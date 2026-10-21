"""pyATS AEtest connectivity tests for the SR Linux lab."""

import sys
from pathlib import Path

from pyats import aetest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.testbed import Testbed  # noqa: E402


TESTBED = Testbed.from_yaml()
CONNECTIVITY_CASES = TESTBED.connectivity_tests


class CommonSetup(aetest.CommonSetup):
    """Validate the loaded testbed before test execution."""

    @aetest.subsection
    def validate_testbed(self):
        if not CONNECTIVITY_CASES:
            self.failed("No connectivity tests found in configs/lab-expanded.yaml")


class ConnectivityValidation(aetest.Testcase):
    """Validate connectivity targets defined in lab.yaml."""

    @aetest.test.loop(
        uids=[case["name"] for case in CONNECTIVITY_CASES],
        test_case=CONNECTIVITY_CASES,
    )
    def verify_connectivity(self, test_case):
        source = TESTBED.router(test_case["source"])
        destination = test_case["destination"]

        command = (
            f"ping {destination} "
            f"network-instance {TESTBED.network_instance} -c 3"
        )

        try:
            output = source.execute(command, timeout=30)
        except Exception as exc:
            self.failed(
                f'{test_case["name"]}: CLI execution failed: {exc}'
            )

        if "3 received" not in output or "0% packet loss" not in output:
            self.failed(
                f'{test_case["name"]}: connectivity validation failed.\n'
                f"Command: {command}\n"
                f"Output:\n{output}"
            )

        self.passed(
            f'{test_case["name"]}: three replies received, '
            "0% packet loss."
        )


if __name__ == "__main__":
    aetest.main()
