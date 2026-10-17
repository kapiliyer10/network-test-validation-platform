"""Proof of concept: native pyATS testbed with SR Linux."""

import re
import sys
from pathlib import Path

from pyats import aetest
from pyats.topology import loader


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

TESTBED_PATH = PROJECT_ROOT / "configs" / "pyats-testbed.yaml"
TESTBED = loader.load(str(TESTBED_PATH))
DEVICE_NAMES = list(TESTBED.devices)


class CommonSetup(aetest.CommonSetup):
    """Validate the native pyATS testbed."""

    @aetest.subsection
    def validate_testbed(self):
        if not DEVICE_NAMES:
            self.failed("The native pyATS testbed contains no devices.")


class NativeTestbedConnectionValidation(aetest.Testcase):
    """Verify each device through the native pyATS connection."""

    @aetest.test.loop(
        uids=DEVICE_NAMES,
        device_name=DEVICE_NAMES,
    )
    def verify_device_command(self, device_name):
        device = TESTBED.devices[device_name]
        connected = False

        try:
            device.connect(via="cli")
            connected = True

            output = device.execute("show version")

        except Exception as exc:
            self.failed(
                f"{device_name}: connection or command failed: {exc}"
            )
            return

        finally:
            if connected:
                device.disconnect()

        match = re.search(
            r"^\s*Hostname\s*:\s*(\S+)\s*$",
            output,
            re.MULTILINE,
        )

        if match is None:
            self.failed(
                f"{device_name}: hostname was not found in "
                f"show version output.\n{output}"
            )

        actual_hostname = match.group(1)

        if actual_hostname != device_name:
            self.failed(
                f"Expected hostname {device_name}, "
                f"received {actual_hostname}"
            )

        self.passed(
            f"{device_name}: native pyATS connection and "
            "show version validation passed."
        )


if __name__ == "__main__":
    aetest.main()
