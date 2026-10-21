
import sys

from docker.errors import DockerException

from src.lab_discovery import discover_lab_routers
from src.testbed import Testbed


def main() -> int:
    """Verify that the Project 1 lab is ready for testing."""
    try:
        testbed = Testbed.from_yaml()
        expected_routers = set(testbed.routers)
        routers = discover_lab_routers()
    except DockerException as exc:
        print(
            f"NOT READY: Cannot access the Docker environment: {exc}",
            file=sys.stderr,
        )
        return 1

    missing = expected_routers - routers.keys()
    stopped = {
        name: routers[name].status
        for name in expected_routers & routers.keys()
        if routers[name].status != "running"
    }

    if missing or stopped:
        print(f"Configured lab {testbed.name!r} is NOT READY.")

        for name in sorted(missing):
            print(f"  MISSING: {testbed.routers[name].container_name}")

        for name, status in sorted(stopped.items()):
            print(f"  NOT RUNNING: {name} (status: {status})")

        return 1

    print(f"Configured lab {testbed.name!r} is READY.")
    print("Running routers: R1, R2, R3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
