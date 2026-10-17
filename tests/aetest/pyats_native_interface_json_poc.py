"""Proof of concept: validate SR Linux interface state using JSON."""

import json
import sys
from pathlib import Path

import yaml
from pyats import aetest
from pyats.topology import loader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

CONFIG_PATH = PROJECT_ROOT / "configs" / "lab.yaml"
TESTBED_PATH = PROJECT_ROOT / "configs" / "pyats-testbed.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)

TESTBED = loader.load(str(TESTBED_PATH))
INTERFACE_CASES = LAB_CONFIG.get("interface_tests", [])

TEST_CASE_NAME = "R1_ethernet_1_1_up"

TEST_CASE = next(
    (
        case
        for case in INTERFACE_CASES
        if case["name"] == TEST_CASE_NAME
    ),
    None,
)


class CommonSetup(aetest.CommonSetup):
    """Validate the test scenario and native pyATS testbed."""

    @aetest.subsection
    def validate_configuration(self):
        if TEST_CASE is None:
            self.failed(
                f"Interface scenario {TEST_CASE_NAME!r} "
                "was not found in configs/lab.yaml"
            )

        router_name = TEST_CASE["router"]

        if router_name not in TESTBED.devices:
            self.failed(
                f"Device {router_name!r} is not defined "
                "in the native pyATS testbed"
            )


class NativePyATSInterfaceJSONValidation(aetest.Testcase):
    """Validate interface state from structured JSON."""

    @aetest.test
    def verify_interface_state(self):
        router_name = TEST_CASE["router"]
        interface_name = TEST_CASE["interface"]
        expected_state = TEST_CASE["expected_state"].lower()

        device = TESTBED.devices[router_name]
        connected = False

        try:
            device.connect(via="cli")
            connected = True

            output = device.execute(
                "show interface | as json",
                timeout=30,
            )

            data = json.loads(output)

        except Exception as exc:
            self.failed(
                f"{TEST_CASE_NAME}: could not collect or parse "
                f"interface data: {exc}"
            )
            return

        finally:
            if connected:
                device.disconnect()

        interfaces = data.get("interfaces")

        if not isinstance(interfaces, list):
            self.failed(
                "JSON response does not contain an interfaces list."
            )

        interface_data = next(
            (
                item
                for item in interfaces
                if item.get("name") == interface_name
            ),
            None,
        )

        if interface_data is None:
            self.failed(
                f"{router_name}: interface {interface_name!r} "
                "was not found in JSON output."
            )

        actual_state = interface_data.get("oper-state", "").lower()

        if actual_state != expected_state:
            self.failed(
                f"{TEST_CASE_NAME}: unexpected operational state. "
                f"Expected {expected_state!r}, "
                f"received {actual_state!r}."
            )

        self.passed(
            f"{router_name} {interface_name}: "
            f"structured JSON reports oper-state={actual_state!r}."
        )


if __name__ == "__main__":
    aetest.main()
