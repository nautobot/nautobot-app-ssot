# Changelog

## v1.1.2 - 2022-05-09

### Fixed

- [#48](https://github.com/nautobot/nautobot-plugin-ssot/pull/48) - Fix introduced bug in #43, using a nonexistent method in an object.

## v1.1.1 - 2022-05-06

### Added

- [#43](https://github.com/nautobot/nautobot-plugin-ssot/pull/43) - The detailed SSoT log output contains a summary info message about the diff changes.

### Fixed

- [#42](https://github.com/nautobot/nautobot-plugin-ssot/pull/42) - Use format_html to create all HTML pieces in render_diff and combine with mark_safe when is formatted twice.
- [#40](https://github.com/nautobot/nautobot-plugin-ssot/pull/40) - Handle gracefully unexpected input type for humanize_bytes filter.

## v1.1.0 - 2022-02-03

### Added

- [#11](https://github.com/nautobot/nautobot-plugin-ssot/issues/11) - Add option to profile memory usage during job execution.
- [#14](https://github.com/nautobot/nautobot-plugin-ssot/pull/14), [#22](https://github.com/nautobot/nautobot-plugin-ssot/pull/22) - Added Prefix sync to example jobs, added Celery worker to dev environment.
- [#15](https://github.com/nautobot/nautobot-plugin-ssot/pull/15) - Added `load_source_adapter`, `load_target_adapter`, `calculate_diff`, and `execute_sync` API methods that Job implementations can override instead of overriding the generalized `sync_data` method.
- [#21](https://github.com/nautobot/nautobot-plugin-ssot/pull/21) - Add performance stats in Sync job detail view.

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
