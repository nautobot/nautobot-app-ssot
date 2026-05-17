"""Smoke tests asserting each integration's `jobs` and `signals` modules import cleanly.

Catches circular imports, broken optional-dependency wiring, and missing module-level imports
that would otherwise only surface when an enabled integration is loaded at app startup.
"""

import importlib
from pathlib import Path

from django.test import TestCase

INTEGRATIONS_DIR = Path(__file__).resolve().parent.parent / "integrations"


def _integration_names():
    """Yield every integration directory that ships real Python source.

    Skips `__pycache__` and any directory that contains no top-level `.py` files
    (currently `servicenow2026`, which is a placeholder for in-progress work).
    """
    for path in sorted(INTEGRATIONS_DIR.iterdir()):
        if not path.is_dir() or path.name == "__pycache__":
            continue
        if not any(p.suffix == ".py" for p in path.glob("*.py")):
            continue
        yield path.name


class TestIntegrationModuleImports(TestCase):
    """Smoke tests covering import-time correctness of every integration's `jobs` and `signals` modules."""

    def test_jobs_modules_import_cleanly(self):
        """Every integration shipping a `jobs.py` module or `jobs/` package must import without raising.

        Iterates with `subTest` so a failure clearly identifies the offending integration
        instead of aborting the whole suite at the first error.
        """
        for name in _integration_names():
            module_path = INTEGRATIONS_DIR / name
            if not (module_path / "jobs.py").exists() and not (module_path / "jobs").is_dir():
                continue
            with self.subTest(integration=name):
                importlib.import_module(f"nautobot_ssot.integrations.{name}.jobs")

    def test_signals_modules_import_cleanly(self):
        """Every integration shipping a `signals.py` module must import without raising.

        Signals are loaded at app `ready()` only for *enabled* integrations, so unit tests
        otherwise never exercise these imports. This guard catches breakage early.
        """
        for name in _integration_names():
            if not (INTEGRATIONS_DIR / name / "signals.py").exists():
                continue
            with self.subTest(integration=name):
                importlib.import_module(f"nautobot_ssot.integrations.{name}.signals")
