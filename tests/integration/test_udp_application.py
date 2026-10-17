"""Application-level UDP connectivity tests."""

from pathlib import Path
import subprocess

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONFIG_PATH = PROJECT_ROOT / "configs" / "lab-expanded.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)


UDP_CLIENT_SCRIPT = """
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
payload = sys.argv[3].encode()
expected = sys.argv[4].encode()

with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    client.settimeout(5)
    client.sendto(payload, (host, port))
    response, address = client.recvfrom(4096)

if response != expected:
    print(f"Expected: {expected!r}")
    print(f"Received: {response!r}")
    sys.exit(1)

print(f"UDP application response verified: {response.decode()}")
"""

@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("udp_application_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_udp_application_exchange(test_case):
    lab = LAB_CONFIG["lab"]
    client_container = (
        f'{lab["container_prefix"]}{test_case["client"]}'
    )

    command = [
        "docker",
        "exec",
        client_container,
        "python3",
        "-c",
        UDP_CLIENT_SCRIPT,
        test_case["destination"],
        str(test_case["port"]),
        test_case["payload"],
        test_case["expected_response"],
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f'{test_case["name"]}: UDP application test timed out. '
            f"Client: {client_container}, "
            f"destination: {test_case['destination']}:"
            f"{test_case['port']}. Error: {exc}"
        )

    assert result.returncode == 0, (
        f'{test_case["name"]}: UDP application exchange failed.\n'
        f"Client: {client_container}\n"
        f"Destination: {test_case['destination']}:"
        f"{test_case['port']}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
