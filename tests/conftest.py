"""
pytest configuration and fixtures for chargerlab tests.

Central place for:
- Async test setup
- Shared fixtures (e.g., power supply)
- Test discovery settings
"""

import pytest


def pytest_configure(config):
    """
    Register custom pytest markers.
    This is already defined in pyproject.toml but we ensure it's available here.
    """
    # Markers are defined in pyproject.toml [tool.pytest.ini_options]
    pass
