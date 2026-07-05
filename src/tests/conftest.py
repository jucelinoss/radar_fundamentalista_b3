"""pytest configuration for integration tests."""
import pytest


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
