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

ROUTE_LINE_PATTERN = re.compile(
    r"^\s*"
    r"(?P<prefix>\d{1,3}(?:\.\d{1,3}){3}/\d+)\s+"
    r"(?P<route_type>\S+)\s+"
    r"\d+\s+\d+\s+"
    r"(?P<flags>\S+)\s+"
    r"(?P<next_hop>\d{1,3}(?:\.\d{1,3}){3})"
    r"\((?P<interface>[^)]+)\)\s*$",
    re.MULTILINE,
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

def parse_route(output, prefix):
    """Return the parsed route matching a prefix, or None."""

    for match in ROUTE_LINE_PATTERN.finditer(output):
        if match.group("prefix") == prefix:
            return match.groupdict()

    return None


def get_route(device, prefix):
    """Read the route table and find the requested prefix."""

    command = (
        f"show network-instance {NETWORK_INSTANCE} ipv4 route all"
    )
    output = device.execute(command, timeout=30)
    return parse_route(output, prefix)

def route_matches(route, expected_next_hop, expected_interface):
    """Return whether the route uses the expected best path."""

    return (
        route is not None
        and route.get("route_type", "").lower() == "ospfv2"
        and route.get("next_hop") == expected_next_hop
        and route.get("interface") == expected_interface
        and ">" in route.get("flags", "")
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
        failover_destination = test_case["failover_destination"]
        failover_prefix = f"{failover_destination}/32"

        expected_failover_next_hop = test_case[
            "expected_failover_next_hop"
        ]
        expected_failover_interface = test_case[
            "expected_failover_interface"
        ]
        expected_recovery_next_hop = test_case[
            "expected_recovery_next_hop"
        ]
        expected_recovery_interface = test_case[
            "expected_recovery_interface"
        ]
        convergence_timeout = test_case["convergence_timeout_seconds"]

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

            baseline_route = get_route(device, failover_prefix)

            if not route_matches(
                baseline_route,
                expected_recovery_next_hop,
                expected_recovery_interface,
            ):
                raise RuntimeError(
                    "Baseline route is not using the expected direct path. "
                    f"Expected next hop {expected_recovery_next_hop} "
                    f"on {expected_recovery_interface}; "
                    f"observed route: {baseline_route}"
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

                        # Wait for OSPF to select the alternate path through R3.
            convergence_deadline = (
                time.monotonic() + convergence_timeout
            )
            observed_failover_route = None
            last_route_error = None

            while time.monotonic() < convergence_deadline:
                try:
                    observed_failover_route = get_route(
                        device,
                        failover_prefix,
                    )
                    last_route_error = None

                    if route_matches(
                        observed_failover_route,
                        expected_failover_next_hop,
                        expected_failover_interface,
                    ):
                        break

                except Exception as exc:
                    last_route_error = (
                        f"{type(exc).__name__}: {exc}"
                    )

                time.sleep(2)

            else:
                raise RuntimeError(
                    "OSPF did not select the expected alternate route "
                    f"within {convergence_timeout} seconds.\n"
                    f"Expected next hop: {expected_failover_next_hop}\n"
                    f"Expected interface: {expected_failover_interface}\n"
                    f"Observed route: {observed_failover_route}\n"
                    f"Last route error: {last_route_error}"
                )

                        # Verify end-to-end reachability over the alternate path.
            failover_ping_command = (
                f"ping {failover_destination} "
                f"network-instance {NETWORK_INSTANCE} "
                f"-c {packet_count}"
            )

            failover_ping_output = device.execute(
                failover_ping_command,
                timeout=30,
                check_returncode=False,
            )
            failover_ping_stats = parse_ping_stats(
                failover_ping_output
            )

            expected_failover_ping = (
                packet_count,
                packet_count,
                0,
            )

            if failover_ping_stats != expected_failover_ping:
                raise RuntimeError(
                    "R2's loopback was not reachable through the "
                    "expected alternate path.\n"
                    f"Expected ping statistics: "
                    f"{expected_failover_ping}\n"
                    f"Observed: {failover_ping_stats}\n"
                    f"Output:\n{failover_ping_output}"
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
                                "enter candidate private",
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

                        if recovery_stats is not None:
                            # Wait for OSPF to restore the direct route.
                            route_deadline = (
                                time.monotonic() + convergence_timeout
                            )
                            observed_recovery_route = None
                            last_route_error = None

                            while time.monotonic() < route_deadline:
                                try:
                                    observed_recovery_route = get_route(
                                        device,
                                        failover_prefix,
                                    )
                                    last_route_error = None

                                    if route_matches(
                                        observed_recovery_route,
                                        expected_recovery_next_hop,
                                        expected_recovery_interface,
                                    ):
                                        break

                                except Exception as exc:
                                    last_route_error = (
                                        f"{type(exc).__name__}: {exc}"
                                    )

                                time.sleep(2)

                            else:
                                recovery_problems.append(
                                    "OSPF did not restore the expected "
                                    "direct route within "
                                    f"{convergence_timeout} seconds.\n"
                                    f"Expected next hop: "
                                    f"{expected_recovery_next_hop}\n"
                                    f"Expected interface: "
                                    f"{expected_recovery_interface}\n"
                                    f"Observed route: "
                                    f"{observed_recovery_route}\n"
                                    f"Last route error: {last_route_error}"
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
