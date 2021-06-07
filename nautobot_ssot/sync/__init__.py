"""Basic API for data sync sources/targets (workers)."""
import pkg_resources


def get_data_sources():
    """Get a list of registered sync worker data sources."""
    # TODO: add option for caching to avoid unnecessary re-loading
    return sorted(
        [
            entrypoint.load() for entrypoint in pkg_resources.iter_entry_points("nautobot_ssot.data_sources")
        ],
        key=lambda worker: worker.name,
    )


def get_data_targets():
    """Get a list of registered sync worker data targets."""
    # TODO: add option for caching to avoid unnecessary re-loading
    return sorted(
        [
            entrypoint.load() for entrypoint in pkg_resources.iter_entry_points("nautobot_ssot.data_targets")
        ],
        key=lambda worker: worker.name,
    )


def get_data_source(name=None, slug=None):
    """Look up the specified data source class."""
    # TODO: add option for caching to avoid unnecessary re-loading
    for data_source in get_data_sources():
        if name and data_source.name != name:
            continue
        if slug and data_source.slug != slug:
            continue
        return data_source
    raise KeyError(f'No data source "{name or slug}" found!')


def get_data_target(name=None, slug=None):
    """Look up the specified data target class."""
    # TODO: add option for caching to avoid unnecessary re-loading
    for data_target in get_data_targets():
        if name and data_target.name != name:
            continue
        if slug and data_target.slug != slug:
            continue
        return data_target
    raise KeyError(f'No data target "{name or slug}" found!')
