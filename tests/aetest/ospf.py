"""pyATS AEtest cases for OSPF neighbor validation."""

import re
import sys
from pathlib import Path

from pyats import aetest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.testbed import Testbed  # noqa: E402


TESTBED = Testbed.from_yaml()
OSPF_CASES = TESTBED.ospf_neighbor_tests


class CommonSetup(aetest.CommonSetup):
    """Validate OSPF test definitions before execution."""

    @aetest.subsection
    def validate_testbed(self):
        if not OSPF_CASES:
            self.failed(
                "No OSPF neighbor tests found in configs/lab-expanded.yaml"
            )


class OSPFNeighborValidation(aetest.Testcase):
    """Verify expected OSPF neighbors and adjacency states."""

    @aetest.test.loop(
        uids=[case["name"] for case in OSPF_CASES],
        test_case=OSPF_CASES,
    )
    def verify_ospf_neighbor(self, test_case):
        router_name = test_case["router"]
        interface = test_case["interface"]
        neighbor_id = test_case["neighbor_router_id"]
        expected_state = test_case["expected_state"].lower()

        router = TESTBED.router(router_name)

        command = (
            f"show network-instance {TESTBED.network_instance} "
            "protocols ospf neighbor"
        )

        try:
            output = router.execute(command, timeout=30)
        except Exception as exc:
            self.failed(
                f'{test_case["name"]}: OSPF command execution failed: {exc}'
            )
            return

        # Match the exact interface and neighbor ID in one table row.
        pattern = re.compile(
            rf"^\|\s*{re.escape(interface)}\s+"
            rf"{re.escape(neighbor_id)}\s+"
            r"(?P<state>[A-Za-z_-]+)\b",
            re.IGNORECASE | re.MULTILINE,
        )

        match = pattern.search(output)

        if match is None:
            self.failed(
                f'{test_case["name"]}: expected OSPF neighbor was not found.\n'
                f"Router: {router_name}\n"
                f"Interface: {interface}\n"
                f"Neighbor router ID: {neighbor_id}\n"
                f"Command: {command}\n"
                f"Output:\n{output}"
            )
            return

        actual_state = match.group("state").lower()

        if actual_state != expected_state:
            self.failed(
                f'{test_case["name"]}: unexpected OSPF adjacency state.\n'
                f"Router: {router_name}\n"
                f"Interface: {interface}\n"
                f"Neighbor router ID: {neighbor_id}\n"
                f"Expected state: {expected_state}\n"
                f"Actual state: {actual_state}"
            )
            return

        self.passed(
            f"{router_name} {interface} -> {neighbor_id}: "
            f"expected state {expected_state}, "
            f"observed state {actual_state}."
        )


if __name__ == "__main__":
    aetest.main()
