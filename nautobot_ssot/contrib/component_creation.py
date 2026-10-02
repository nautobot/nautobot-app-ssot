"""SSoT integration with Nautobot core's SkipAutoComponentCreation extension point.

Re-exports :class:`nautobot.apps.dcim.SkipAutoComponentCreation` and
:func:`nautobot.apps.dcim.is_auto_component_creation_suppressed` when running
against a Nautobot version that ships them (the upstream extension point is
proposed in https://github.com/nautobot/nautobot/issues/9026 and tracked by
https://github.com/nautobot/nautobot/pull/9027).

On older Nautobot versions where the upstream symbol is unavailable, the
re-exports fall back to a no-op context manager and a function that always
returns ``False``. The fallback context manager emits a one-shot logger
warning the first time it is entered, so opt-in users can see why their
suppression is not taking effect rather than the feature silently doing
nothing.

Apps should import these names from :mod:`nautobot_ssot.contrib` (or from
this module) rather than directly from :mod:`nautobot.apps.dcim`, so the
upgrade path remains forward-compatible.
"""

import logging

logger = logging.getLogger(__name__)


try:
    from nautobot.apps.dcim import (  # pylint: disable=unused-import
        SkipAutoComponentCreation,
        is_auto_component_creation_suppressed,
    )

    _UPSTREAM_AVAILABLE = True
except ImportError:
    _UPSTREAM_AVAILABLE = False

    class SkipAutoComponentCreation:
        """No-op fallback when the upstream ``nautobot.apps.dcim`` API is unavailable.

        Emits a one-shot logger warning the first time the context is entered so
        opt-in users see why suppression is not taking effect. The context
        manager otherwise behaves like a no-op: it does not raise and does not
        affect the wrapped block.
        """

        _warned = False

        def __enter__(self):
            """Emit a one-shot warning that the upstream API is unavailable; otherwise no-op."""
            cls = type(self)
            if not cls._warned:
                logger.warning(
                    "nautobot.apps.dcim.SkipAutoComponentCreation is not available in "
                    "this Nautobot installation; SSoT's skip_auto_component_creation "
                    "opt-in will be a no-op. Upgrade Nautobot to a version that ships "
                    "the upstream extension point to use this feature."
                )
                cls._warned = True
            return self

        def __exit__(self, exc_type, exc, tb):
            """Do not suppress exceptions raised inside the with block."""
            return False

    def is_auto_component_creation_suppressed() -> bool:
        """Return ``False`` always; the upstream extension point is unavailable."""
        return False


def upstream_available() -> bool:
    """Return ``True`` if Nautobot core's ``SkipAutoComponentCreation`` API is importable."""
    return _UPSTREAM_AVAILABLE
