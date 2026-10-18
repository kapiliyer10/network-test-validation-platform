"""Configuration-driven iperf3 UDP performance tests."""

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
    LAB_CONFIG.get("iperf3_udp_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_iperf3_udp_performance(test_case):
    lab = LAB_CONFIG["lab"]
    prefix = lab["container_prefix"]

    client_container = f'{prefix}{test_case["client"]}'
    server_container = f'{prefix}{test_case["server"]}'

    command = [
        "docker", "exec", client_container,
        "iperf3",
        "-c", test_case["destination"],
        "-p", str(test_case["port"]),
        "-u",
        "-b", f'{test_case["target_bitrate_mbps"]}M',
        "-t", str(test_case["duration_seconds"]),
        "-i", str(test_case["interval_seconds"]),
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
            f'{test_case["name"]}: iperf3 UDP test timed out. '
            f"Client: {client_container}; server: {server_container}; "
            f"error: {exc}"
        )

    assert result.returncode == 0, (
        f'{test_case["name"]}: iperf3 UDP test failed.\n'
        f"Client: {client_container}\n"
        f"Server: {server_container}\n"
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    try:
        report = json.loads(result.stdout)
        received = report["end"]["sum_received"]

        receiver_mbps = (
            float(received["bits_per_second"]) / 1_000_000
        )
        jitter_ms = float(received["jitter_ms"])
        lost_packets = int(received["lost_packets"])
        total_packets = int(received["packets"])
        loss_percent = float(received["lost_percent"])
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        pytest.fail(
            f'{test_case["name"]}: invalid iperf3 UDP JSON results: {exc}\n'
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    print(
        f'{test_case["name"]}: '
        f'receiver={receiver_mbps:.3f} Mbps, '
        f'loss={loss_percent:.3f}% '
        f'({lost_packets}/{total_packets} packets), '
        f'jitter={jitter_ms:.3f} ms, '
        f'target={test_case["target_bitrate_mbps"]} Mbps'
    )

    assert receiver_mbps >= test_case["min_receiver_mbps"], (
        f'{test_case["name"]}: receiver throughput below threshold. '
        f'Expected at least {test_case["min_receiver_mbps"]:.2f} Mbps; '
        f'observed {receiver_mbps:.3f} Mbps.'
    )

    assert loss_percent <= test_case["max_loss_percent"], (
        f'{test_case["name"]}: packet loss exceeded threshold. '
        f'Allowed {test_case["max_loss_percent"]:.3f}%; '
        f'observed {loss_percent:.3f}% '
        f'({lost_packets}/{total_packets} packets).'
    )

    assert jitter_ms <= test_case["max_jitter_ms"], (
        f'{test_case["name"]}: jitter exceeded threshold. '
        f'Allowed {test_case["max_jitter_ms"]:.3f} ms; '
        f'observed {jitter_ms:.3f} ms.'
    )
