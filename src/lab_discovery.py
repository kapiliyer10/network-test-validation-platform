import docker
from docker.models.containers import Container

CONTAINER_PREFIX = "clab-srl-lab-"


def discover_lab_routers() -> dict[str, Container]:
    """Discover Project 1 router containers through Docker."""
    client = docker.from_env()
    containers = client.containers.list(all=True)

    routers = {
        container.name[len(CONTAINER_PREFIX):]: container
        for container in containers
        if container.name.startswith(CONTAINER_PREFIX)
    }

    return routers
