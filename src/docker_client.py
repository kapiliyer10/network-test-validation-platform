import docker


def get_container(name: str):
    """Return a running Docker container by name."""
    client = docker.from_env()
    container = client.containers.get(name)

    if container.status != "running":
        raise RuntimeError(f"Container is not running: {name}")

    return container
