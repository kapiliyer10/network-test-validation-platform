
"""Discover configured router containers through Docker."""

import docker
from docker.models.containers import Container

from src.testbed import Testbed


def discover_lab_routers() -> dict[str, Container]:
    """Discover configured routers for the selected testbed."""
    testbed = Testbed.from_yaml()
    client = docker.from_env()

    try:
        containers = client.containers.list(all=True)

        expected_containers = {
            device.container_name: router_name
            for router_name, device in testbed.routers.items()
        }

        routers = {
            expected_containers[container.name]: container
            for container in containers
            if container.name in expected_containers
        }

        return routers
    finally:
        client.close()
