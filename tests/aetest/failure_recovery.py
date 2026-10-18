"""Controlled interface failure and recovery using native pyATS."""

import re
import sys
import time
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
TEST_CASES = LAB_CONFIG.get("failure_recovery_tests", [])
NETWORK_INSTANCE = LAB_CONFIG["lab"]["network_instance"]

PING_STATS_PATTERN = re.compile(
    r"(?P<transmitted>\d+)\s+packets transmitted,\s*"
    r"(?P<received>\d+)\s+received,\s*"
    r"(?P<loss>\d+)%\s+packet loss"
)


def parse_ping_stats(output):
    """Return (transmitted, received, loss_percent) from ping output."""

    match = PING_STATS_PATTERN.search(output)

    if not match:
        raise RuntimeError(
            "Could not parse ping statistics from output:\n"
            f"{output}"
        )

    return (
        int(match.group("transmitted")),
        int(match.group("received")),
        int(match.group("loss")),
    )


class CommonSetup(aetest.CommonSetup):
    """Validate test definitions and native pyATS devices."""

    @aetest.subsection
    def validate_testbed(self):
        if not TEST_CASES:
            self.failed(
                "No failure-recovery tests found in configs/lab.yaml"
            )

        for case in TEST_CASES:
            router = case["router"]

            if router not in TESTBED.devices:
                self.failed(
                    f'{case["name"]}: router {router!r} is not '
                    "defined in the native pyATS testbed"
                )

            if case["rollback_timeout_seconds"] <= 0:
                self.failed(
                    f'{case["name"]}: rollback timeout must be positive'
                )


class FailureRecoveryValidation(aetest.Testcase):
    """Verify a controlled link failure and subsequent recovery."""

    @aetest.test.loop(
        uids=[case["name"] for case in TEST_CASES],
        test_case=TEST_CASES,
    )
    def verify_failure_and_recovery(self, test_case):
        test_name = test_case["name"]
        router_name = test_case["router"]
        interface = test_case["interface"]
        destination = test_case["destination"]
        packet_count = test_case["expected_packets"]
        rollback_timeout = test_case["rollback_timeout_seconds"]

        device = TESTBED.devices[router_name]
        connection = None
        connected = False
        commit_may_be_pending = False

        failure_problem = None
        recovery_problems = []
        rollback_problem = None

        ping_command = (
            f"ping {destination} "
            f"network-instance {NETWORK_INSTANCE} "
            f"-c {packet_count}"
        )

        try:
            device.connect(via="cli")
            connected = True
            connection = device.connectionmgr.connections["default"]

            # Establish a healthy baseline before disrupting the link.
            admin_output = device.execute(
                f"info interface {interface} admin-state",
                timeout=30,
            )
            if "admin-state enable" not in admin_output:
                raise RuntimeError(
                    f"{interface} is not administratively enabled "
                    "before the test"
                )

            interface_output = device.execute(
                f"show interface {interface}",
                timeout=30,
            )
            if not re.search(
                rf"{re.escape(interface)} is up\b",
                interface_output,
            ):
                raise RuntimeError(
                    f"{interface} is not operationally up "
                    "before the test"
                )

            baseline_output = device.execute(
                ping_command,
                timeout=30,
            )
            expected_baseline = (
                packet_count,
                packet_count,
                0,
            )
            baseline_stats = parse_ping_stats(baseline_output)

            if baseline_stats != expected_baseline:
                raise RuntimeError(
                    "Connectivity baseline is not healthy. "
                    f"Expected {expected_baseline}; "
                    f"observed {baseline_stats}"
                )

            # The timer is the fallback if immediate cleanup fails.
            commit_may_be_pending = True

            change_output = connection.execute_commands(
                [
                    "enter candidate private",
                    f"interface {interface} admin-state disable",
                    f"commit confirmed timeout {rollback_timeout}",
                ],
                timeout=30,
            )

            if "Commit confirmed" not in change_output:
                raise RuntimeError(
                    "SR Linux did not acknowledge the confirmed commit.\n"
                    f"Output:\n{change_output}"
                )

            # A ping with expected packet loss may have exit code 1.
            failure_output = device.execute(
                ping_command,
                timeout=30,
                check_returncode=False,
            )

            failure_stats = parse_ping_stats(failure_output)
            expected_failure = (
                packet_count,
                0,
                100,
            )

            if failure_stats != expected_failure:
                raise RuntimeError(
                    "The expected connectivity failure was not observed. "
                    f"Expected {expected_failure}; "
                    f"observed {failure_stats}\n"
                    f"Output:\n{failure_output}"
                )

        except Exception as exc:
            failure_problem = f"{type(exc).__name__}: {exc}"

        finally:
            if connected:
                # Attempt immediate rollback before checking recovery.
                if commit_may_be_pending:
                    try:
                        rollback_output = connection.execute_commands(
                            [
                                "tools system configuration confirmed-reject",
                            ],
                            timeout=30,
                        )
                        print(
                            f"{test_name}: rollback command output:\n"
                            f"{rollback_output}"
                        )
                    except Exception as exc:
                        rollback_problem = (
                            f"{type(exc).__name__}: {exc}"
                        )

                # Verify actual state; do not trust the command response
                # alone. Allow a short period for the interface to recover.
                try:
                    interface_recovered = False
                    last_admin_output = ""
                    last_interface_output = ""

                    for _ in range(15):
                        last_admin_output = device.execute(
                            f"info interface {interface} admin-state",
                            timeout=30,
                        )
                        last_interface_output = device.execute(
                            f"show interface {interface}",
                            timeout=30,
                        )

                        enabled = (
                            "admin-state enable" in last_admin_output
                        )
                        operationally_up = bool(
                            re.search(
                                rf"{re.escape(interface)} is up\b",
                                last_interface_output,
                            )
                        )

                        if enabled and operationally_up:
                            interface_recovered = True
                            break

                        time.sleep(1)

                    if not interface_recovered:
                        recovery_problems.append(
                            f"{interface} was not confirmed enabled and up. "
                            "The confirmed-commit rollback timer remains "
                            "the safety fallback. Verify the router state "
                            "before running any further tests.\n"
                            f"Administrative state:\n{last_admin_output}\n"
                            f"Interface state:\n{last_interface_output}"
                        )
                    else:
                        # Require real replies after restoring the link.
                        expected_recovery = (
                           packet_count,
                           packet_count,
                           0,
                        )
                        recovery_stats = None
                        last_recovery_stats = None
                        last_recovery_output = ""

                        for attempt in range(1, 11):
                            try:
                                recovery_output = device.execute(
                                    ping_command,
                                    timeout=15,
                                    check_returncode=False,
                                )
                                last_recovery_output = recovery_output
                                observed_stats = parse_ping_stats(
                                    recovery_output
                                )
                                last_recovery_stats = observed_stats

                                if observed_stats == expected_recovery:
                                    recovery_stats = observed_stats
                                    break

                            except Exception as exc:
                                last_recovery_output = (
                                    f"{type(exc).__name__}: {exc}"
                                )

                            if attempt < 10:
                                time.sleep(2)

                        if recovery_stats is None:
                            recovery_problems.append(
                                "Connectivity did not recover within "
                                "10 ping attempts. "
                                f"Expected {expected_recovery}; "
                                f"last observed statistics: "
                                f"{last_recovery_stats}\n"
                                f"Last output:\n{last_recovery_output}"
                            )

                except Exception as exc:
                    recovery_problems.append(
                        f"Recovery verification raised "
                        f"{type(exc).__name__}: {exc}"
                    )

                finally:
                    device.disconnect()

        if failure_problem:
            self.failed(
                f"{test_name}: failure phase did not complete correctly.\n"
                f"{failure_problem}"
            )
            return

        if recovery_problems:
            self.failed(
                f"{test_name}: recovery verification failed.\n"
                + "\n".join(recovery_problems)
            )
            return

        message = (
            f"{test_name}: expected link failure observed, "
            "interface enabled and up, and ping connectivity recovered."
        )

        if rollback_problem:
            message += (
                " The rollback command returned an error, but the final "
                "interface and connectivity checks passed. Review the "
                f"rollback response: {rollback_problem}"
            )

        self.passed(message)


if __name__ == "__main__":
    aetest.main()
