"""Proof of concept: connectivity validation using native pyATS devices."""

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

NETWORK_INSTANCE = LAB_CONFIG["lab"]["network_instance"]
CONNECTIVITY_CASES = LAB_CONFIG.get("connectivity_tests", [])

TEST_CASE_NAME = "R1_to_R2"

TEST_CASE = next(
    (
        case
        for case in CONNECTIVITY_CASES
        if case["name"] == TEST_CASE_NAME
    ),
    None,
)


class CommonSetup(aetest.CommonSetup):
    """Validate configuration before running the test."""

    @aetest.subsection
    def validate_configuration(self):
        if TEST_CASE is None:
            self.failed(
                f"Connectivity scenario {TEST_CASE_NAME!r} "
                "was not found in configs/lab.yaml"
            )

        source_name = TEST_CASE["source"]

        if source_name not in TESTBED.devices:
            self.failed(
                f"Device {source_name!r} is not defined "
                "in the native pyATS testbed"
            )


class NativePyATSConnectivityValidation(aetest.Testcase):
    """Validate R1-to-R2 connectivity through native pyATS."""

    @aetest.test
    def verify_connectivity(self):
        source_name = TEST_CASE["source"]
        destination = TEST_CASE["destination"]

        device = TESTBED.devices[source_name]

        command = (
            f"ping {destination} "
            f"network-instance {NETWORK_INSTANCE} -c 3"
        )

        connected = False

        try:
            device.connect(via="cli")
            connected = True

            output = device.execute(command, timeout=30)

        except Exception as exc:
            self.failed(
                f"{TEST_CASE_NAME}: command execution failed.\n"
                f"Command: {command}\n"
                f"Error: {exc}"
            )

        finally:
            if connected:
                device.disconnect()

        if (
            "3 received" not in output
            or "0% packet loss" not in output
        ):
            self.failed(
                f"{TEST_CASE_NAME}: connectivity validation failed.\n"
                f"Command: {command}\n"
                f"Output:\n{output}"
            )

        self.passed(
            f"{TEST_CASE_NAME}: three replies received, "
            "0% packet loss."
        )


if __name__ == "__main__":
    aetest.main()
