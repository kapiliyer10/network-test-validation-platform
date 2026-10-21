from src.lab_discovery import discover_lab_routers
import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.expanded_lab,
]

def test_expanded_lab_routers_are_discovered_and_running():
    routers = discover_lab_routers()

    expected_routers = {"R1", "R2", "R3"}

    missing_routers = expected_routers - routers.keys()
    assert not missing_routers, (
        f"Expanded-lab routers not discovered: {sorted(missing_routers)}"
    )

    for router_name in sorted(expected_routers):
        assert routers[router_name].status == "running", (
            f"{router_name} is not running: "
            f"{routers[router_name].status}"
        )
