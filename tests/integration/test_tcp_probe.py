"""TCP probe response tests for the expanded SR Linux lab."""

from pathlib import Path
import re
import os
import pytest
import yaml

from src.cli_runner import run_router_cli_command

pytestmark = pytest.mark.expanded_lab
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = Path(
    os.environ.get(
        "NETWORK_TESTBED_CONFIG",
        str(PROJECT_ROOT / "configs" / "lab-expanded.yaml"),
    )
).expanduser()

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)


TCP_RESPONSE_PATTERN = re.compile(
    r"<(?:rst,ack|syn,ack)>",
    re.IGNORECASE,
)


@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG["connectivity_tests"],
    ids=lambda test_case: test_case["name"],
)
def test_tcp_probe_receives_response(test_case):
    lab = LAB_CONFIG["lab"]

    container_name = (
        f'{lab["container_prefix"]}{test_case["source"]}'
    )
    destination = test_case["destination"]
    network_instance = lab["network_instance"]

    command = (
        f"tcptraceroute {destination} "
        f"network-instance {network_instance}"
    )

    output = run_router_cli_command(
        container_name=container_name,
        command=command,
    )

    assert TCP_RESPONSE_PATTERN.search(output), (
        f'{test_case["name"]}: no TCP SYN/ACK or RST/ACK '
        f"response observed.\n"
        f"Command: {command}\n"
        f"Output:\n{output}"
    )
