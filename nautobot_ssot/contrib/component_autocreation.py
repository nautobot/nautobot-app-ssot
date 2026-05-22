"""Opt-in suppression of Nautobot's automatic Device/Module component instantiation.

When a new ``Device`` or ``Module`` is saved, Nautobot calls
``create_components()`` from within ``save()``, instantiating one component per
template defined on the related ``DeviceType``/``ModuleType``. For Single
Source of Truth (SSoT) sync jobs this is almost always undesirable: the source
of truth owns the component inventory, and the auto-created components either
collide with or pollute what the sync is about to write.

This module exposes three opt-in mechanisms (in order of granularity):

1. ``skip_component_autocreation`` -- a context manager that suppresses
   autocreation for any code that runs inside it.
2. A ``skip_component_autocreation = True`` class attribute on
   :class:`nautobot_ssot.jobs.base.DataSyncBaseJob` subclasses (wired up in
   ``jobs/base.py``).
3. A global ``skip_component_autocreation`` flag in
   ``PLUGINS_CONFIG["nautobot_ssot"]`` (also wired in ``jobs/base.py``).

The underlying mechanism is a process-wide monkey-patch installed once at app
startup via :func:`install_patches`. The patch wraps
``Device.create_components`` and ``Module.create_components`` with a thin
shim that consults a :class:`contextvars.ContextVar`. When the flag is unset
(the default), behaviour is unchanged; when set, the wrapped method becomes a
no-op and returns an empty list.

The patch is idempotent so it is safe under Django autoreload, and stores a
reference to the original method on the wrapper so :func:`uninstall_patches`
can restore the unmodified behaviour (primarily useful for tests).
"""

import contextvars
import functools
import logging

logger = logging.getLogger(__name__)


_skip_flag: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "nautobot_ssot_skip_component_autocreation",
    default=False,
)


class skip_component_autocreation:  # noqa: N801 — intentional lowercase, matches stdlib (suppress, nullcontext)
    """Context manager that suppresses Device/Module component autocreation.

    Inside the ``with`` block, ``Device.create_components()`` and
    ``Module.create_components()`` become no-ops. The original behaviour is
    restored automatically on exit, including when the block raises.

    Nested usage is supported; each context manager instance saves and
    restores its own token, so an outer ``with`` block continues to suppress
    after an inner block exits.

    Implementation uses :mod:`contextvars`, so the flag is correctly scoped
    per asyncio task / Celery worker invocation and does not leak across
    threads.

    Example:
        >>> from nautobot_ssot.contrib import skip_component_autocreation
        >>> from nautobot.dcim.models import Device
        >>> with skip_component_autocreation():
        ...     device = Device.objects.create(...)  # no auto-components
    """

    def __init__(self):
        """Initialize without entering the context yet."""
        self._token: contextvars.Token | None = None

    def __enter__(self):
        """Activate suppression for the calling context."""
        self._token = _skip_flag.set(True)
        return self

    def __exit__(self, exc_type, exc, tb):
        """Restore the previous suppression state."""
        if self._token is not None:
            _skip_flag.reset(self._token)
            self._token = None
        # Do not suppress exceptions raised inside the with block.
        return False


def is_suppression_active() -> bool:
    """Return whether component autocreation is currently suppressed.

    Intended for tests and adapter code that wants to make decisions based on
    whether it is running inside a :class:`skip_component_autocreation`
    block. Production code should normally use the context manager directly.
    """
    return _skip_flag.get()


def _build_wrapper(original):
    """Build a wrapper around an ``alters_data`` model method.

    The wrapper delegates to ``original`` unless the suppression flag is
    active, in which case it returns an empty list and logs at DEBUG level.

    Args:
        original: The bound-method-like callable being wrapped (typically
            ``Device.create_components`` or ``Module.create_components``).

    Returns:
        A new callable suitable for assigning back to the model class. The
        wrapper exposes ``_ssot_wrapped = True`` and ``_ssot_original`` for
        introspection and cleanup.
    """

    @functools.wraps(original)
    def wrapper(self):
        if _skip_flag.get():
            logger.debug(
                "SSoT suppressed create_components() for %s pk=%s",
                type(self).__name__,
                self.pk,
            )
            return []
        return original(self)

    # Django checks ``alters_data`` on methods to refuse calling them from
    # templates. Preserve it on the wrapper so behaviour is unchanged.
    wrapper.alters_data = True
    wrapper._ssot_wrapped = True
    wrapper._ssot_original = original
    return wrapper


def install_patches() -> None:
    """Install the ``create_components`` wrappers on ``Device`` and ``Module``.

    Called once from ``NautobotSSOTAppConfig.ready()``. Safe to call multiple
    times -- already-wrapped methods are detected via the ``_ssot_wrapped``
    sentinel and left alone, so Django's autoreload behaviour does not stack
    wrappers.

    Failures (e.g. Nautobot internals changed in a way the patch does not
    understand) are logged but not raised, so app startup is never blocked by
    this opt-in feature.
    """
    try:
        # Import lazily so this module remains importable for doc generation
        # and unit tests that do not boot a full Nautobot environment.
        from nautobot.dcim.models import Device, Module
    except ImportError:
        logger.exception(
            "Could not import nautobot.dcim.models.{Device,Module}; skip_component_autocreation will be unavailable."
        )
        return

    for model in (Device, Module):
        original = model.create_components
        if getattr(original, "_ssot_wrapped", False):
            logger.debug(
                "%s.create_components already wrapped by SSoT; skipping.",
                model.__name__,
            )
            continue
        model.create_components = _build_wrapper(original)
        logger.debug("Wrapped %s.create_components with SSoT suppression shim.", model.__name__)


def uninstall_patches() -> None:
    """Restore the original ``create_components`` methods.

    Primarily intended for test teardown. Idempotent: if a method is not
    currently wrapped by this app, it is left alone.
    """
    try:
        from nautobot.dcim.models import Device, Module
    except ImportError:
        return

    for model in (Device, Module):
        current = model.create_components
        original = getattr(current, "_ssot_original", None)
        if original is not None:
            model.create_components = original
            logger.debug("Restored original %s.create_components.", model.__name__)
