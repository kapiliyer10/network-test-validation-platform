"""Integration tests for SR Linux connectivity."""

import pytest

from src.testbed import Testbed


TESTBED = Testbed.from_yaml()


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    TESTBED.connectivity_tests,
    ids=lambda test_case: test_case["name"],
)
def test_router_connectivity(test_case):
    source = TESTBED.router(test_case["source"])
    destination = test_case["destination"]

    command = (
        f"ping {destination} "
        f"network-instance {TESTBED.network_instance} -c 3"
    )

    output = source.execute(command)

    assert "3 received" in output, (
        f'{test_case["name"]}: expected 3 received packets.\n'
        f"Command: {command}\nOutput:\n{output}"
    )

    assert "0% packet loss" in output, (
        f'{test_case["name"]}: expected 0% packet loss.\n'
        f"Command: {command}\nOutput:\n{output}"
    )
