"""
Shared pytest configuration for all test files.

Provides:
  - MockResponse / RateLimitedResponse classes (importable from conftest)
  - --run-network CLI option
  - Custom markers (network, slow)
  - Automatic skip of network tests unless --run-network is passed
"""
import os
import sys

# Ensure src/ is in path for all test files
SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pytest


# ---------------------------------------------------------------------------
# Shared mock HTTP response classes
# ---------------------------------------------------------------------------

class MockResponse:
    """Reusable mock for requests.get responses.

    Usage:
        mock_get.return_value = MockResponse({"key": "value"})
    """

    def __init__(self, data: dict, status: int = 200):
        self._data = data
        self.status_code = status

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._data


class RateLimitedResponse:
    """Mock for a 429 Rate Limited HTTP response."""

    status_code = 429

    def raise_for_status(self) -> None:
        from requests.exceptions import HTTPError
        raise HTTPError("429 Too Many Requests")

    def json(self) -> dict:
        return {}


# ---------------------------------------------------------------------------
# pytest hooks
# ---------------------------------------------------------------------------

def pytest_addoption(parser):
    parser.addoption(
        "--run-network", action="store_true", default=False,
        help="Run tests that call external APIs (Yahoo Finance, brapi.dev)"
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "network: tests that call external APIs (need internet)")
    config.addinivalue_line("markers", "slow: tests that take more than 10 seconds")


def pytest_collection_modifyitems(config, items):
    """Skip network tests unless --run-network is passed."""
    if config.getoption("--run-network"):
        return  # Let all tests run
    skip_network = pytest.mark.skip(reason="Use --run-network to enable API tests")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip_network)
