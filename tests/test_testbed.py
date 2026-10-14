"""Unit tests for the Project 2 testbed abstraction."""

import pytest

from src.testbed import Testbed


@pytest.fixture
def configuration():
    return {
        "lab": {
            "name": "unit-lab",
            "container_prefix": "clab-unit-",
            "network_instance": "default",
            "routers": ["R1", "R2", "R3"],
        },
        "connectivity_tests": [],
    }


@pytest.mark.unit
def test_router_resolves_container_name(configuration):
    testbed = Testbed(configuration)

    assert testbed.router("R1").container_name == "clab-unit-R1"
    assert testbed.router("R2").container_name == "clab-unit-R2"
    assert testbed.network_instance == "default"


@pytest.mark.unit
def test_unknown_router_raises_clear_error(configuration):
    testbed = Testbed(configuration)

    with pytest.raises(KeyError, match="Router 'R4' is not defined"):
        testbed.router("R4")


@pytest.mark.unit
def test_duplicate_router_names_are_rejected(configuration):
    configuration["lab"]["routers"] = ["R1", "R1"]

    with pytest.raises(ValueError, match="Router names must be unique"):
        Testbed(configuration)


@pytest.mark.unit
def test_missing_lab_mapping_is_rejected():
    with pytest.raises(ValueError, match="must contain a 'lab' mapping"):
        Testbed({})
