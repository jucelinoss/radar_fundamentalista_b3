"""pytest configuration for integration tests."""
import pytest


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "network: tests that call Yahoo Finance API (need internet)")
    config.addinivalue_line("markers", "slow: tests that take more than 10 seconds")
