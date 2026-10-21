"""Negative connectivity tests using native pyATS devices."""

import re
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
TEST_CASES = LAB_CONFIG.get("negative_connectivity_tests", [])

PING_STATS_PATTERN = re.compile(
    r"(?P<transmitted>\d+)\s+packets transmitted,\s*"
    r"(?P<received>\d+)\s+received,\s*"
    r"(?P<loss>\d+)%\s+packet loss"
)


class CommonSetup(aetest.CommonSetup):
    """Validate negative connectivity test definitions."""

    @aetest.subsection
    def validate_testbed(self):
        if not TEST_CASES:
            self.failed(
                "No negative connectivity tests found "
                "in configs/lab-expanded.yaml"
            )

        for case in TEST_CASES:
            source = case["source"]

            if source not in TESTBED.devices:
                self.failed(
                    f'{case["name"]}: source router {source!r} '
                    "is not defined in the native pyATS testbed"
                )


class NegativeConnectivityValidation(aetest.Testcase):
    """Verify that expected network unreachability is detected."""

    @aetest.test.loop(
        uids=[case["name"] for case in TEST_CASES],
        test_case=TEST_CASES,
    )
    def verify_expected_packet_loss(self, test_case):
        test_name = test_case["name"]
        source_name = test_case["source"]
        destination = test_case["destination"]

        expected_transmitted = test_case["expected_transmitted"]
        expected_received = test_case["expected_received"]
        expected_loss = test_case["expected_packet_loss_percent"]

        device = TESTBED.devices[source_name]
        command = (
            f"ping {destination} "
            f"network-instance default "
            f"-c {expected_transmitted}"
        )

        connected = False

        try:
            device.connect(via="cli")
            connected = True

            # A ping with no replies may return exit code 1.
            # Allow the runner to return its statistics for validation.
            output = device.execute(
                command,
                timeout=30,
                check_returncode=False,
            )

        except Exception as exc:
            self.failed(
                f"{test_name}: could not execute the negative "
                f"connectivity check.\n"
                f"Router: {source_name}\n"
                f"Command: {command}\n"
                f"Error: {exc}"
            )
            return

        finally:
            if connected:
                device.disconnect()

        match = PING_STATS_PATTERN.search(output)

        if not match:
            self.failed(
                f"{test_name}: could not parse ping statistics.\n"
                f"Command: {command}\n"
                f"Output:\n{output}"
            )
            return

        transmitted = int(match.group("transmitted"))
        received = int(match.group("received"))
        packet_loss = int(match.group("loss"))

        observed = (transmitted, received, packet_loss)
        expected = (
            expected_transmitted,
            expected_received,
            expected_loss,
        )

        if observed != expected:
            self.failed(
                f"{test_name}: observed connectivity results "
                "did not match expectations.\n"
                f"Expected (transmitted, received, loss %): "
                f"{expected}\n"
                f"Observed: {observed}\n"
                f"Output:\n{output}"
            )
            return

        self.passed(
            f"{test_name}: expected packet loss confirmed "
            f"({transmitted} transmitted, {received} received, "
            f"{packet_loss}% loss)."
        )


if __name__ == "__main__":
    aetest.main()
