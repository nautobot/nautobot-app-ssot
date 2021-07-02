# Developing Data Source and Data Target Jobs

A goal of this plugin is to make it relatively quick and straightforward to develop and integrate your own system-specific Data Sources and Data Targets into Nautobot with a common UI and user experience.

Familiarity with [DiffSync](https://diffsync.readthedocs.io/en/latest/) and with developing [Nautobot Jobs](https://nautobot.readthedocs.io/en/latest/additional-features/jobs/) is recommended.

In brief, the following general steps can be followed:

1. Define one or more `DiffSyncModel` data model class(es) representing the common data record(s) to be synchronized between the two systems.
    
    * For each model class, implement the `create`, `update`, and `delete` DiffSyncModel APIs for writing data to the Data Target system.

2. Define a `DiffSync` adapter class for loading initial data from Nautobot and constructing instances of each `DiffSyncModel` class to represent that data.
3. Define a `DiffSync` adapter class for loading initial data from the Data Source or Data Target system and constructing instances of the `DiffSyncModel` classes to represent that data.
4. Develop a Job class, derived from either the `DataSource` or `DataTarget` classes provided by this plugin, and implement its `sync_data` API function to make use of the DiffSync adapters and data models defined previously. Typically this will look something like:

        def sync_data(self):
            """Sync data from Data Source to Nautobot."""
            self.log_info(message="Loading current data from Data Source...")
            diffsync1 = DataSourceDiffSync(job=self, sync=self.sync)
            diffsync1.load()

            self.log_info(message="Loading current data from Nautobot...")
            diffsync2 = NautobotDiffSync(job=self, sync=self.sync)
            diffsync2.load()

            diffsync_flags = DiffSyncFlags.CONTINUE_ON_FAILURE

            self.log_info(message="Calculating diffs...")
            diff = diffsync1.diff_to(diffsync_1, flags=diffsync_flags)
            self.sync.diff = diff.dict()
            self.sync.save()

            if not self.kwargs["dry_run"]:
                self.log_info(message="Syncing from Data Source to Nautobot...")
                diffsync1.sync_to(diffsync2, flags=diffsync_flags)
                self.log_info(message="Sync complete")

5. Optionally, on your Job class, also implement the `lookup_object`, `data_mappings`, and/or `config_information` APIs (to provide more information to the end user about the details of this Job), as well as the various metadata properties on your Job's `Meta` inner class. Refer to the example Jobs provided in this plugin for examples and further details.
6. Install your Job via any of the supported Nautobot methods (installation into the `JOBS_ROOT` directory, inclusion in a Git repository, or packaging as part of a plugin) and it should automatically become available!
