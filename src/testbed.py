"""Minimal testbed abstraction for the existing SR Linux lab."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.cli_runner import run_router_cli_command


DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1]
    / "configs"
    / "lab.yaml"
)


@dataclass(frozen=True)
class RouterDevice:
    """Reference to a router in the existing Containerlab."""

    name: str
    container_name: str

    def execute(
        self,
        command: str,
        timeout: float = 30,
    ) -> str:
        """Execute one SR Linux CLI command."""
        return run_router_cli_command(
            container_name=self.container_name,
            command=command,
            timeout=timeout,
        )


class Testbed:
    """Resolve logical router names using the lab configuration."""

    __test__ = False

    def __init__(self, configuration: dict[str, Any]) -> None:
        lab = configuration.get("lab")

        if not isinstance(lab, dict):
            raise ValueError(
                "Lab configuration must contain a 'lab' mapping"
            )

        self.name = lab["name"]
        self.container_prefix = lab["container_prefix"]
        self.network_instance = lab["network_instance"]

        router_names = lab.get("routers", [])

        if not router_names:
            raise ValueError(
                "Lab configuration must define at least one router"
            )

        if len(router_names) != len(set(router_names)):
            raise ValueError("Router names must be unique")

        self.routers = {
            name: RouterDevice(
                name=name,
                container_name=f"{self.container_prefix}{name}",
            )
            for name in router_names
        }

        self.connectivity_tests = configuration.get(
            "connectivity_tests", []
        )

    @classmethod
    def from_yaml(
        cls,
        path: str | Path = DEFAULT_CONFIG_PATH,
    ) -> "Testbed":
        """Load the existing Project 2 lab configuration."""
        config_path = Path(path)

        with config_path.open(encoding="utf-8") as config_file:
            configuration = yaml.safe_load(config_file)

        if not isinstance(configuration, dict):
            raise ValueError(
                f"Invalid lab configuration: {config_path}"
            )

        return cls(configuration)

    def router(self, name: str) -> RouterDevice:
        """Look up a configured router by its logical name."""
        try:
            return self.routers[name]
        except KeyError as exc:
            raise KeyError(
                f"Router {name!r} is not defined "
                f"in testbed {self.name!r}"
            ) from exc
