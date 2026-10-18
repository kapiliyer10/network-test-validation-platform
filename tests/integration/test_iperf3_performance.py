"""Configuration-driven iperf3 TCP performance tests."""

import json
from pathlib import Path
import subprocess

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "lab-expanded.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("iperf3_tcp_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_iperf3_tcp_throughput(test_case):
    lab = LAB_CONFIG["lab"]
    prefix = lab["container_prefix"]

    client_container = f'{prefix}{test_case["client"]}'
    server_container = f'{prefix}{test_case["server"]}'

    command = [
        "docker", "exec", client_container,
        "iperf3",
        "-c", test_case["destination"],
        "-p", str(test_case["port"]),
        "-t", str(test_case["duration_seconds"]),
        "-i", str(test_case["interval_seconds"]),
        "-M", str(test_case["tcp_mss_bytes"]),
        "-b", f'{test_case["target_bitrate_mbps"]}M',
        "-J",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=test_case["duration_seconds"] + 30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(
            f'{test_case["name"]}: iperf3 timed out. '
            f"Client: {client_container}; server: {server_container}; "
            f"error: {exc}"
        )

    assert result.returncode == 0, (
        f'{test_case["name"]}: iperf3 failed.\n'
        f"Client: {client_container}\n"
        f"Server: {server_container}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    try:
        report = json.loads(result.stdout)
        end = report["end"]
        receiver_bps = float(
            end["sum_received"]["bits_per_second"]
        )
        retransmits = int(end["sum_sent"]["retransmits"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        pytest.fail(
            f'{test_case["name"]}: invalid iperf3 JSON results: {exc}\n'
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    receiver_mbps = receiver_bps / 1_000_000
    print(
        f'{test_case["name"]}: '
        f'receiver={receiver_mbps:.2f} Mbps, '
        f'retransmissions={retransmits}, '
        f'target={test_case["target_bitrate_mbps"]} Mbps'
    )
    minimum_mbps = test_case["min_receiver_mbps"]
    maximum_retransmits = test_case["max_retransmits"]

    assert receiver_mbps >= minimum_mbps, (
        f'{test_case["name"]}: receiver throughput below threshold. '
        f"Expected at least {minimum_mbps:.2f} Mbps; "
        f"observed {receiver_mbps:.2f} Mbps."
    )

    assert retransmits <= maximum_retransmits, (
        f'{test_case["name"]}: TCP retransmissions exceeded threshold. '
        f"Allowed {maximum_retransmits}; observed {retransmits}. "
        f"Receiver throughput: {receiver_mbps:.2f} Mbps."
    )
