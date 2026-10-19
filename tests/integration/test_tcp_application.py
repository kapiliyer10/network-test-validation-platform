"""Application-level TCP connectivity tests with packet-capture artifacts."""

from pathlib import Path
import subprocess

import pytest
import yaml

from src.packet_capture import PacketCapture


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "lab-expanded.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)


TCP_CLIENT_SCRIPT = """
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
payload = sys.argv[3].encode()
expected = sys.argv[4].encode()

with socket.create_connection((host, port), timeout=5) as client:
    client.sendall(payload)

    response = b""
    while len(response) < len(expected):
        chunk = client.recv(4096)
        if not chunk:
            break
        response += chunk

if response != expected:
    print(f"Expected: {expected!r}")
    print(f"Received: {response!r}")
    sys.exit(1)

print(f"TCP application response verified: {response.decode()}")
"""


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("tcp_application_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_tcp_application_exchange(test_case):
    lab = LAB_CONFIG["lab"]
    client_container = f'{lab["container_prefix"]}{test_case["client"]}'
    output_path = (
        PROJECT_ROOT
        / "artifacts"
        / "pcap"
        / f'{test_case["name"]}.pcap'
    )

    capture = PacketCapture(
        container=client_container,
        interface="eth1",
        capture_filter=(
            f'host {test_case["destination"]} '
            f'and tcp port {test_case["port"]}'
        ),
        output_path=output_path,
    )

    command = [
        "docker",
        "exec",
        client_container,
        "python3",
        "-c",
        TCP_CLIENT_SCRIPT,
        test_case["destination"],
        str(test_case["port"]),
        test_case["payload"],
        test_case["expected_response"],
    ]

    capture.start()
    try:
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
                f'{test_case["name"]}: TCP application test timed out. '
                f"Client: {client_container}, "
                f"destination: {test_case['destination']}:"
                f"{test_case['port']}. Error: {exc}"
            )

        assert result.returncode == 0, (
            f'{test_case["name"]}: TCP application exchange failed.\n'
            f"Client: {client_container}\n"
            f"Destination: {test_case['destination']}:"
            f"{test_case['port']}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    finally:
        capture.stop()

    assert capture.packet_count > 0, (
        f'{test_case["name"]}: no packets matched the capture filter. '
        f"PCAP: {output_path}"
    )

    print(
        f'{test_case["name"]}: captured {capture.packet_count} packets; '
        f"PCAP saved to {output_path}"
    )
