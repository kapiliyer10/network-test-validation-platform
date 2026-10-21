"""LLDP neighbor validation using native pyATS devices."""

import json
import sys
from pathlib import Path

import yaml
from pyats import aetest
from pyats.topology import loader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_PATH = PROJECT_ROOT / "configs" / "lab-expanded.yaml"
TESTBED_PATH = PROJECT_ROOT / "configs" / "pyats-testbed.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)

TESTBED = loader.load(str(TESTBED_PATH))
LLDP_CASES = LAB_CONFIG.get("lldp_neighbor_tests", [])


class CommonSetup(aetest.CommonSetup):
    """Validate LLDP test definitions and native pyATS devices."""

    @aetest.subsection
    def validate_testbed(self):
        if not LLDP_CASES:
            self.failed(
                "No LLDP neighbor tests found in configs/lab-expanded.yaml"
            )

        for case in LLDP_CASES:
            router_name = case["router"]

            if router_name not in TESTBED.devices:
                self.failed(
                    f'{case["name"]}: router {router_name!r} '
                    "is not defined in the native pyATS testbed"
                )


class LLDPNeighborValidation(aetest.Testcase):
    """Compare discovered LLDP neighbors with expected topology."""

    @aetest.test.loop(
        uids=[case["name"] for case in LLDP_CASES],
        test_case=LLDP_CASES,
    )
    def verify_lldp_neighbor(self, test_case):
        test_name = test_case["name"]
        router_name = test_case["router"]
        local_interface = test_case["local_interface"]
        expected_neighbor = test_case["expected_neighbor"]
        expected_neighbor_port = test_case["expected_neighbor_port"]

        device = TESTBED.devices[router_name]
        connected = False
        command = "show system lldp neighbor | as json"

        try:
            device.connect(via="cli")
            connected = True

            output = device.execute(command, timeout=30)
            data = json.loads(output)

        except Exception as exc:
            self.failed(
                f"{test_name}: could not collect or parse LLDP data.\n"
                f"Router: {router_name}\n"
                f"Command: {command}\n"
                f"Error: {exc}"
            )
            return

        finally:
            if connected:
                device.disconnect()

        neighbors = data.get("LLDP-Interface")

        if not isinstance(neighbors, list):
            self.failed(
                f"{test_name}: JSON output has no "
                "'LLDP-Interface' list."
            )
            return

        local_neighbors = [
            entry
            for entry in neighbors
            if isinstance(entry, dict)
            and entry.get("Name") == local_interface
        ]

        expected_found = any(
            entry.get("Neighbor System Name") == expected_neighbor
            and entry.get("Neighbor Port") == expected_neighbor_port
            for entry in local_neighbors
        )

        if not expected_found:
            observed = [
                {
                    "neighbor": entry.get("Neighbor System Name"),
                    "neighbor_port": entry.get("Neighbor Port"),
                }
                for entry in local_neighbors
            ]

            self.failed(
                f"{test_name}: expected LLDP neighbor was not found.\n"
                f"Router: {router_name}\n"
                f"Local interface: {local_interface}\n"
                f"Expected neighbor: {expected_neighbor}\n"
                f"Expected neighbor port: {expected_neighbor_port}\n"
                f"Observed neighbors: {observed}"
            )
            return

        self.passed(
            f"{router_name} {local_interface} discovers "
            f"{expected_neighbor} on {expected_neighbor_port}."
        )


if __name__ == "__main__":
    aetest.main()
