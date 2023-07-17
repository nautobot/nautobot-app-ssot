# Copy of `pysnow`

`pysnow` is currently pinned to an older version of `pytz` as a dependency, which blocks compatibility with newer
versions of Nautobot. [See](https://github.com/rbw/pysnow/pull/186).

For now, we have embedded a copy of `pysnow` under `nautobot_ssot/integrations/servicenow/third_party/pysnow`.

All `pysnow` dependencies are defined as an extra dependency in `pyproject.toml`
