# Changelog

## v1.1.0 - YYYY-MM-DD

### Added

- [#11](https://github.com/nautobot/nautobot-plugin-ssot/issues/11) - Add option to profile memory usage during job execution.
- [#14](https://github.com/nautobot/nautobot-plugin-ssot/pull/14) - Added Prefix sync to example jobs, added Celery worker to dev environment.
- [#15](https://github.com/nautobot/nautobot-plugin-ssot/pull/15) - Added `load_source_adapter`, `load_target_adapter`, `calculate_diff`, and `execute_sync` API methods that Job implementations can override instead of overriding the generalized `sync_data` method.

### Fixed

- [#13](https://github.com/nautobot/nautobot-plugin-ssot/issues/13) - Handle pagination of Nautobot REST API in example jobs.
- [#18](https://github.com/nautobot/nautobot-plugin-ssot/pull/18) - Don't skip diff and sync if either of the source or target adapters initially contains no data.

## v1.0.1 - 2021-10-18

### Changed

- [#8](https://github.com/nautobot/nautobot-plugin-ssot/pull/8) - Switched from Travis CI to GitHub Actions.

### Fixed

- [#9](https://github.com/nautobot/nautobot-plugin-ssot/pull/9) - Added missing `name` string to `jobs/examples.py`.

### Removed

- [#7](https://github.com/nautobot/nautobot-plugin-ssot/pull/7) - Removed unnecessary `markdown-include` development/documentation dependency.

## v1.0.0 - 2021-07-28

Initial public release
