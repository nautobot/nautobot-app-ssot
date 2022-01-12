# Developing Data Source and Data Target Jobs

A goal of this plugin is to make it relatively quick and straightforward to develop and integrate your own system-specific Data Sources and Data Targets into Nautobot with a common UI and user experience.

Familiarity with [DiffSync](https://diffsync.readthedocs.io/en/latest/) and with developing [Nautobot Jobs](https://nautobot.readthedocs.io/en/latest/additional-features/jobs/) is recommended.

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
     def load_source_adapter(self):
         """Method to instantiate and load the SOURCE adapter into `self.source_adapter`."""
         self.source_adapter = NautobotRemote(url=self.kwargs["source_url"], token=self.kwargs["source_token"], job=self)
         self.source_adapter.load()
     ```

   - `self.calculate_diff`: This method is implemented by default, using the output from load_adapter methods.

   - `self.execute_sync`: This method is implemented by default, using the output from load_adapter methods. Only executed if it's not a `dry-run` execution.

5. Optionally, on your Job class, also implement the `lookup_object`, `data_mappings`, and/or `config_information` APIs (to provide more information to the end user about the details of this Job), as well as the various metadata properties on your Job's `Meta` inner class. Refer to the example Jobs provided in this plugin for examples and further details.
6. Install your Job via any of the supported Nautobot methods (installation into the `JOBS_ROOT` directory, inclusion in a Git repository, or packaging as part of a plugin) and it should automatically become available!

## Analyze Job performance

The built-in implementation of `sync_data` is composed by 4 steps:

- Loading data from source adapter
- Loading data from target adapter
- Calculating diff
- Executing synchronization (if not `dry-run`)

For each one of these 4 steps we can capture data for performance analysis:

- Time spent: available in the "Data Sync" detail view under Duration section
- Memory used at the end of the step execution: available in the "Data Sync" detail view under Memory Usage Stats section
- Peak Memory used during the step execution: available in the "Data Sync" detail view under Memory Usage Stats section

> Memory performance stats are optional, and you must enable them per Job execution with the related checkbox.

This data could give you some insights about where most of the time is spent and how efficient in memory your process is (if there is a big difference between the peak and the final numbers is a hint of something not going well). Understanding it, you could focus on the step that needs more attention.
