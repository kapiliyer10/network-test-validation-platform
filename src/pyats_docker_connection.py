"""pyATS connection adapter for Docker-hosted SR Linux routers."""

import subprocess

from pyats.connections import BaseConnection

from src.cli_runner import run_router_cli_command


class DockerSRLConnection(BaseConnection):
    """Execute SR Linux CLI commands through the Docker CLI runner."""

    def __init__(
        self,
        *,
        device,
        alias,
        via,
        container_name=None,
        **kwargs,
    ):
        super().__init__(
            device=device,
            alias=alias,
            via=via,
            **kwargs,
        )

        device_custom = getattr(device, "custom", {}) or {}

        self.container_name = (
            container_name
            or device_custom.get("container_name")
        )

        if not self.container_name:
            raise ValueError(
                f"No Docker container name configured for "
                f"device {device.name!r}"
            )

        self._connected = False

    @property
    def connected(self):
        """Return the logical connection state."""
        return self._connected

    @property
    def connection_info(self):
        """Describe how this adapter reaches the device."""
        return {
            "transport": "docker exec",
            "container_name": self.container_name,
        }

    @BaseConnection.locked
    def connect(self, *args, **kwargs):
        """Verify that the target Docker container is running."""

        try:
            result = subprocess.run(
                [
                    "docker",
                    "inspect",
                    "--format={{.State.Running}}",
                    self.container_name,
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ConnectionError(
                f"Could not check router container "
                f"{self.container_name!r}: {exc}"
            ) from exc

        if (
            result.returncode != 0
            or result.stdout.strip().lower() != "true"
        ):
            detail = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"docker inspect exited with {result.returncode}"
            )

            raise ConnectionError(
                f"Router container {self.container_name!r} "
                f"is not running: {detail}"
            )

        self._connected = True

    @BaseConnection.locked
    def disconnect(self):
        """Mark the logical connection as disconnected."""
        self._connected = False

    @BaseConnection.locked
    def execute(self, command, timeout=30.0):
        """Execute one SR Linux CLI command."""

        if not self.connected:
            raise RuntimeError(
                "Connect the pyATS device before executing commands"
            )

        return run_router_cli_command(
            container_name=self.container_name,
            command=command,
            timeout=timeout,
        )
