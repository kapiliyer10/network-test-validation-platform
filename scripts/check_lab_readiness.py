
import sys

from docker.errors import DockerException

from src.lab_discovery import discover_lab_routers


EXPECTED_ROUTERS = {"R1", "R2", "R3"}


def main() -> int:
    """Verify that the Project 1 lab is ready for testing."""
    try:
        routers = discover_lab_routers()
    except DockerException as exc:
        print(
            f"NOT READY: Cannot access the Docker environment: {exc}",
            file=sys.stderr,
        )
        return 1

    missing = EXPECTED_ROUTERS - routers.keys()
    stopped = {
        name: routers[name].status
        for name in EXPECTED_ROUTERS & routers.keys()
        if routers[name].status != "running"
    }

    if missing or stopped:
        print("Project 1 lab is NOT READY.")

        for name in sorted(missing):
            print(f"  MISSING: clab-srl-lab-{name}")

        for name, status in sorted(stopped.items()):
            print(f"  NOT RUNNING: {name} (status: {status})")

        return 1

    print("Project 1 lab is READY.")
    print("Running routers: R1, R2, R3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
