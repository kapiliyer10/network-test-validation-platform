"""pyATS AEtest cases for SR Linux interface validation."""

import re
import sys
from pathlib import Path

from pyats import aetest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.testbed import Testbed

TESTBED = Testbed.from_yaml()
INTERFACE_CASES = TESTBED.interface_tests

class CommonSetup(aetest.CommonSetup):
    """Check that interface test definitions are available."""

    @aetest.subsection
    def validate_testbed(self):
        if not INTERFACE_CASES:
            self.failed(
                "No interface tests found in configs/lab.yaml"
            )


class InterfaceValidation(aetest.Testcase):
    """Validate interface operational state against expectations."""

    @aetest.test.loop(
        uids=[case["name"] for case in INTERFACE_CASES],
        test_case=INTERFACE_CASES,
    )
    def verify_interface_state(self, test_case):
        router_name = test_case["router"]
        interface = test_case["interface"]
        expected_state = test_case["expected_state"].lower()

        router = TESTBED.router(router_name)

        try:
            output = router.execute("show interface", timeout=30)
        except Exception as exc:
            self.failed(
                f'{test_case["name"]}: command execution failed: {exc}'
            )
            return

        # Match the physical/logical interface header, not its subinterface.
        pattern = re.compile(
            rf"^[ \t]*{re.escape(interface)}[ \t]+is[ \t]+"
            r"(?P<state>[A-Za-z_-]+)\b",
            re.IGNORECASE | re.MULTILINE,
        )

        match = pattern.search(output)

        if match is None:
            self.failed(
                f'{test_case["name"]}: interface {interface!r} '
                f"was not found in the command output.\n"
                f"Router: {router_name}\n"
                f"Output:\n{output}"
            )
            return

        actual_state = match.group("state").lower()

        if actual_state != expected_state:
            self.failed(
                f'{test_case["name"]}: unexpected interface state.\n'
                f"Router: {router_name}\n"
                f"Interface: {interface}\n"
                f"Expected: {expected_state}\n"
                f"Actual: {actual_state}"
            )
            return

        self.passed(
            f"{router_name} {interface}: "
            f"expected state {expected_state}, "
            f"observed state {actual_state}."
        )


if __name__ == "__main__":
    aetest.main()
