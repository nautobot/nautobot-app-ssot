# Developing Data Source and Data Target Jobs

A goal of this plugin is to make it relatively quick and straightforward to develop and integrate your own system-specific Data Sources and Data Targets into Nautobot with a common UI and user experience.

Familiarity with [DiffSync](https://diffsync.readthedocs.io/en/latest/) and with developing [Nautobot Jobs](https://nautobot.readthedocs.io/en/latest/additional-features/jobs/) is recommended.

## Quickstart

In brief, the following general steps can be followed:

1. Define one or more `DiffSyncModel` data model class(es) representing the common data record(s) to be synchronized between the two systems.

   - Define your models based on the data you want to sync. For example, if you are syncing specific attributes (e.g. tags) of a device, but not the devices themselves, your parent model
     should be the tags. This approach prevents unnecessary `create`, `update`, and `delete` calls for models that are not sync'd.
   - For each model class, implement the `create`, `update`, and `delete` DiffSyncModel APIs for writing data to the Data Target system.

2. Define a `DiffSync` adapter class for loading initial data from Nautobot and constructing instances of each `DiffSyncModel` class to represent that data.
3. Define a `DiffSync` adapter class for loading initial data from the Data Source or Data Target system and constructing instances of the `DiffSyncModel` classes to represent that data.

4. Develop a Job class, derived from either the `DataSource` or `DataTarget` classes provided by this plugin, and implement the adapters to populate the `self.source_adapter` and `self.target_adapter` that are used by the built-in implementation of `sync_data`. This `sync_data` method is an opinionated way of running the process including some performance data, more in [next section](#analyze-job-performance), but you could overwrite it completely or any of the key hooks that it calls:

   - `self.load_source_adapter`: This is mandatory to be implemented. As an example:

     ```python
     def load_source_adapter(self):
         """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
         self.source_adapter = NautobotRemote(url=self.kwargs["source_url"], token=self.kwargs["source_token"], job=self)
         self.source_adapter.load()
     ```

   - `self.load_target_adapter`: This is mandatory to be implemented. As an example:

     ```python
     def load_target_adapter(self):
        """Method to instantiate and load the TARGET adapter into `self.target_adapter`."""
        self.target_adapter = NautobotLocal(job=self)
        self.target_adapter.load()
     ```

   - `self.calculate_diff`: This method is implemented by default, using the output from load_adapter methods.

   - `self.execute_sync`: This method is implemented by default, using the output from load_adapter methods. Only executed if it's not a `dry-run` execution.

5. Optionally, on your Job class, also implement the `lookup_object`, `data_mappings`, and/or `config_information` APIs (to provide more information to the end user about the details of this Job), as well as the various metadata properties on your Job's `Meta` inner class. Refer to the example Jobs provided in this plugin for examples and further details.
6. Install your Job via any of the supported Nautobot methods (installation into the `JOBS_ROOT` directory, inclusion in a Git repository, or packaging as part of a plugin) and it should automatically become available!

## Optimizing for Execution Time

When syncing large amounts of data, job execution time may start to become an issue. Fortunately, there are a number of ways you can go about optimizing your jobs performance.

### Optimizing Nautobot Database Queries

As an SSoT job typically has lots of Nautobot database interaction (i.e. Nautobot is always either the source or the destination) for loading, creating, updating, and deleting objects, this is a common source of performance issues.

The following is an example of an inefficient `load` function that can be greatly improved:

```python
from diffsync import DiffSync
from nautobot.dcim.models import Region, Site, Location

from my_package import ParentRegionModel, ChildRegionModel, SiteModel, LocationModel

class ExampleAdapter(DiffSync):
    parent_region = ParentRegionModel
    child_region = ChildRegionModel
    site = SiteModel
    location = LocationModel
    top_level = ("parent_region",)
    
    ...
    
    def load(self):
        for parent_region in Region.objects.filter(parent__isnull=True):
            parent_region_diffsync = self.parent_region(name=parent_region.name)
            self.add(parent_region_diffsync)
            for child_region in Region.objects.filter(parent=parent_region):
                child_region_diffsync = self.child_region(name=child_region.name)
                self.add(child_region_diffsync)
                parent_region_diffsync.add_child(child_region_diffsync)
                for site in Site.objects.filter(region=child_region):
                    site_diffsync = self.site(name=site.name)
                    self.add(site_diffsync)
                    child_region_diffsync.add_child(site_diffsync)
                    for location in Location.objects.filter(site=site):
                        location_diffsync = self.location(name=location.name)
                        self.add(location_diffsync)
                        site_diffsync.add_child(location_diffsync)
        
```

The problem with this admittedly intuitive approach is that each call to `Model.objects.filter()` produces a single database query. This means that if you have 5000 locations under 2000 sites under 30 child regions under 3 parent regions the code will have to issue 7033 database queries. This only gets worse as you add additional data and possible further complexity to this relatively simple example.

Here is a better approach that utilizes diffsync's `get_or_instantiate` and Django's [`select_related`](https://docs.djangoproject.com/en/3.2/ref/models/querysets/#select-related) for query optimization purposes:

```python
def load(self):
    # This next lines represents the single (!) database query that replaces the 7033 from the previous example
    for location in Location.objects.all().select_related("site", "site__region", "site__region__parent"):
        parent_region, parent_region_created = self.get_or_instantiate("parent_region", ids={"name": location.site.region.parent.name})
        if parent_region_created:
            self.add(parent_region)
        child_region, child_region_created = self.get_or_instantiate("child_region", ids={"name": location.site.region.parent})
        if child_region_created:
            self.add(child_region)
            parent_region.add_child(child_region)
        site, site_created = self.get_or_instantiate("site", ids={"name": location.site.name})
        if site_created:
            self.add(site)
            child_region.add_child(site)
        location, location_created = self.get_or_instantiate("location", ids={"name": location.name})
        if location_created:
            self.add(location)
            site.add_child(location)
```

As an additional bonus, this way the code has fewer levels of indentation.

The essence of this is that you should make liberal use of `select_related` to join together the database tables you need into a single, big query rather than a bunch of small queries.

!!! warning
    If you are using Nautobot 1.4 or lower, `CACHEOPS_ENABLED` is set to `True` by default. As long as this is the case, you should use `select_related`'s cousin `prefetch_related` instead (see [here](https://github.com/Suor/django-cacheops#caveats) for cacheops documentation on that matter). In 1.5 this is disabled by default, but if you explicitly turn it on you will again need to use `prefetch_related` instead.
    
    If you are using Nautobot 2.0 or higher, this warning can be ignored as cacheops has been removed from Nautobot. 

!!! note
    Check out the [Django documentation](https://docs.djangoproject.com/en/3.2/topics/db/optimization/) for a more comprehensive source on optimizing database access.

### Optimizing worker stdout IO

If after optimizing your database access you are still facing performance issues, you should check out the [analyzing job performance](#analyzing-job-performance) section of the docs. Should you find that a certain `io.write` appears high up in the ranking, you are probably facing an issue where your job is writing to stdout so quickly that your worker node/process cannot drain its buffer quickly enough. To deal with this, tone down on what you are logging to stdout inside your job. This could be any of the following things (non-exhaustive, check out your worker logs):

- diffsync [logging configuration](https://diffsync.readthedocs.io/en/latest/api/diffsync.logging.html?highlight=logging)
- `print` calls
- other, external frameworks you are using

### Minimizing external IO

In most if not all cases, the side of an SSoT job that interacts with the non-Nautobot system will be accessed through some form of IO as for example HTTP requests via the network. Depending on the amount of requests, request/response size and the latency to the remote system this can take a lot of time. Care should be taken when crafting the IO interaction, using bulk endpoints instead of querying each individual record on the remote system where possible.

Here is an unoptimized high-level workflow:
- Collect sites
  - For each site, collect all devices
    - For each device, collect the interface information
    - For each device, collect the VLAN information

Similar to the database example further up, this suffers from having to perform a lookup (or in this case two) per instance of the lowest item in the hierarchy. It could be optimized (given the availability of bulk endpoints in the remote system) to look something like the following:

- Collect all Sites
- Collect all Devices
- Collect all Interfaces
- Collect all VLANs
- Correlate these data points in code

### Further Possible Optimization Points

Finally, there are a couple of further ideas that could be used to improve performance. These aren't as well analyzed as the prior ones and there might be built-in support in this app for the in the future:

#### Escaping the Atomic Transaction

In Nautobot 1.x, all Jobs are executed in an [atomic transaction](https://en.wikipedia.org/wiki/Atomicity_(database_systems)). Atomic transactions often incur a performance overhead. The following example highlights how to have your sync operation "escape" the atomic transaction:

```python
class DataSource(DataSource, Job):
    ...  # Excluded most of the class definition for example brevity

    def execute_sync(self):
        self.log_info(obj=None, message="The actual sync happens in post_run to escape the atomic transaction.")

    def post_run(self):
        super().execute_sync()
```

Using this example, the CRUD (create, update and delete) operations of your job will not happen as part of the atomic database transaction, because `post_run` is run outside of that. This brings with it the following caveats:

- The job result page in Nautobot will show the status of "Completed" _before_ your actual sync runs
  - You will need to manually update the page to get further job log results
  - The job result might still go into an erroneous state, updating the job result status
- If you implement any further logic in `post_run` keep in mind that it doesn't bubble exceptions up to the job result page in Nautobot
- If any exceptions are encountered during the CRUD operations (i.e. the diffsync models' `create`, `update` and `delete` methods) they will _not_ trigger a rollback of the objects created during this job

Due to these caveats it is recommended that you check carefully whether this optimization actually benefits your use case or not before applying it in production code.

!!! note
  In Nautobot 2.0, jobs will no longer be atomic by default so this section will not apply anymore.

#### Using Bulk ORM Operations

Bulk ORM operations are available within Django to perform multiple inserts/updates in a single DB query. Take a look at the documentation for [bulk_create](https://docs.djangoproject.com/en/3.2/ref/models/querysets/#bulk-create) for example. These bulk operations should only be used very carefully in Nautobot. The following caveats apply when using them:

- No change log is generated
- No model validation is performed (you could for example connect a cable to the same interface on both ends, causing UI views to break)
- No custom `save` methods are called (for the `Device` model for example this causes all device components from the device type not to be created)

Bulk ORM operations can nevertheless be a performance improvement, you just have to be very careful when employing them.

## Analyzing Job Performance

In general there are two different metrics to optimize for when developing SSoT jobs:

- CPU time (maps directly to total execution time)
- Memory usage
- IO

We can capture data for all of these to analyze potential problems.

The built-in implementation of `sync_data`, which is the SSoT job method that encompasses all the computationally expensive steps, is composed of 4 steps:

- Loading data from source adapter
- Loading data from target adapter
- Calculating diff
- Executing synchronization (if the `dry-run` checkbox wasn't ticked)

For each one of these 4 steps we can capture data for performance analysis:

- Time spent: available in the "Data Sync" detail view under "Duration" section
- Memory used at the end of the step execution: available in the "Data Sync" detail view under "Memory Usage Stats" section
- Peak memory usage during the step execution: available in the "Data Sync" detail view under "Memory Usage Stats" section

!!! note
    Memory performance stats are optional, and you must enable them per Job execution with the related checkbox.

If you are running Nautobot 1.5.17 or above and have the `DEBUG` setting enabled in your `nautobot_config.py` you can use [this](https://docs.nautobot.com/projects/core/en/stable/additional-features/jobs/#debugging-job-performance) feature from Nautobot to run a CPU profiler on your job execution, letting you get intricate details on which exact method/function calls are taking up how much time in your SSoT job.

This data could give you some insights about where most of the time is spent and how efficient in memory your process is (if there is a big difference between the peak and the final numbers is a hint of something not going well). Understanding it, you could focus on the step that needs more attention.