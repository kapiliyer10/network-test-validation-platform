"""pyATS AEtest cases for SR Linux route validation."""

import re
import sys
from pathlib import Path

from pyats import aetest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.testbed import Testbed  # noqa: E402


TESTBED = Testbed.from_yaml()
ROUTE_CASES = TESTBED.route_tests

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


class CommonSetup(aetest.CommonSetup):
    """Validate route-test definitions before execution."""

    @aetest.subsection
    def validate_testbed(self):
        if not ROUTE_CASES:
            self.failed("No route tests found in configs/lab-expanded.yaml")


class RouteValidation(aetest.Testcase):
    """Validate expected OSPF-learned routes."""

    @aetest.test.loop(
        uids=[case["name"] for case in ROUTE_CASES],
        test_case=ROUTE_CASES,
    )
    def verify_route(self, test_case):
        router_name = test_case["router"]
        prefix = test_case["prefix"]
        router = TESTBED.router(router_name)

        command = (
            f"show network-instance "
            f"{TESTBED.network_instance} ipv4 route all"
        )

        try:
            output = router.execute(command, timeout=30)
        except Exception as exc:
            self.failed(
                f'{test_case["name"]}: route-table command failed: {exc}'
            )
            return

        routes = {
            match.group("prefix"): match.groupdict()
            for match in ROUTE_LINE_PATTERN.finditer(output)
        }

        actual_route = routes.get(prefix)

        if actual_route is None:
            self.failed(
                f'{test_case["name"]}: expected route was not found.\n'
                f"Router: {router_name}\n"
                f"Prefix: {prefix}\n"
                f"Command: {command}\n"
                f"Output:\n{output}"
            )
            return

        mismatches = []

        checks = (
            (
                "route type",
                test_case["expected_route_type"].lower(),
                actual_route["route_type"].lower(),
            ),
            (
                "next hop",
                test_case["expected_next_hop"],
                actual_route["next_hop"],
            ),
            (
                "interface",
                test_case["expected_interface"],
                actual_route["interface"],
            ),
        )

        for label, expected, actual in checks:
            if actual != expected:
                mismatches.append(
                    f"{label}: expected {expected!r}, got {actual!r}"
                )

        has_best_flag = ">" in actual_route["flags"]

        if has_best_flag != test_case["expected_best"]:
            mismatches.append(
                f'best-route flag: expected '
                f'{test_case["expected_best"]}, '
                f"got {has_best_flag} "
                f'(flags={actual_route["flags"]!r})'
            )

        if mismatches:
            self.failed(
                f'{test_case["name"]}: route validation failed.\n'
                + "\n".join(mismatches)
                + f"\nObserved route: {actual_route}"
            )
            return

        self.passed(
            f'{router_name} {prefix}: route type, next hop, '
            f'interface, and best-route status match expectations.'
        )


if __name__ == "__main__":
    aetest.main()
