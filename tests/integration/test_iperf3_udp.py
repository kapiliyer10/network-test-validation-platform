"""UDP performance, packet-loss, and jitter validation."""

import json
from contextlib import contextmanager
from pathlib import Path
import subprocess

import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "lab-expanded.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)


def docker_exec(container, *args, timeout=10):
    return subprocess.run(
        ["docker", "exec", container, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def run_iperf3_udp(profile, rate_mbps=None):
    """Run iperf3 and return receiver throughput, loss, and jitter."""
    lab = LAB_CONFIG["lab"]
    client_container = f'{lab["container_prefix"]}{profile["client"]}'
    rate = (
        profile["target_bitrate_mbps"]
        if rate_mbps is None
        else rate_mbps
    )

    command = [
        "docker", "exec", client_container,
        "iperf3",
        "-c", profile["destination"],
        "-p", str(profile["port"]),
        "-u",
        "-b", f"{rate}M",
        "-t", str(profile["duration_seconds"]),
        "-i", str(profile["interval_seconds"]),
        "-J",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=profile["duration_seconds"] + 30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        pytest.fail(f'{profile["name"]}: iperf3 timed out: {exc}')

    assert result.returncode == 0, (
        f'{profile["name"]}: iperf3 failed.\n'
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )

    try:
        report = json.loads(result.stdout)
        received = report["end"]["sum_received"]
        return {
            "receiver_mbps": (
                float(received["bits_per_second"]) / 1_000_000
            ),
            "jitter_ms": float(received["jitter_ms"]),
            "lost_packets": int(received["lost_packets"]),
            "total_packets": int(received["packets"]),
            "loss_percent": float(received["lost_percent"]),
        }
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        pytest.fail(
            f'{profile["name"]}: invalid iperf3 UDP JSON: {exc}\n'
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )


def print_udp_result(name, result):
    print(
        f"{name}: "
        f'receiver={result["receiver_mbps"]:.3f} Mbps, '
        f'loss={result["loss_percent"]:.3f}% '
        f'({result["lost_packets"]}/{result["total_packets"]} packets), '
        f'jitter={result["jitter_ms"]:.3f} ms'
    )


@contextmanager
def temporary_netem(container, interface, arguments, expected_state):
    """Apply a netem rule and verify restoration to the original noqueue state."""
    initial = docker_exec(
        container, "tc", "qdisc", "show", "dev", interface
    )
    assert initial.returncode == 0, (
        f"Cannot inspect initial qdisc on {container}:{interface}: "
        f"{initial.stderr}"
    )
    assert initial.stdout.strip().startswith("qdisc noqueue"), (
        f"Refusing to overwrite unexpected qdisc on "
        f"{container}:{interface}:\n{initial.stdout}"
    )

    impairment_attempted = False
    try:
        impairment_attempted = True
        applied = docker_exec(
            container,
            "tc", "qdisc", "replace", "dev", interface,
            "root", "netem", *arguments,
        )
        assert applied.returncode == 0, (
            f"Failed to apply netem impairment to "
            f"{container}:{interface}.\n"
            f"stdout:\n{applied.stdout}\n"
            f"stderr:\n{applied.stderr}"
        )
        yield
    finally:
        if impairment_attempted:
            current = docker_exec(
                container, "tc", "qdisc", "show", "dev", interface
            )
            if current.returncode != 0:
                pytest.fail(
                    f"CRITICAL: cannot inspect qdisc on "
                    f"{container}:{interface}. Inspect and restore "
                    f"the interface manually."
                )

            # Normalize whitespace because tc may print variable spacing.
            state = " ".join(current.stdout.split())
            normalized_expected_state = " ".join(expected_state.split())

            if (
                state.startswith("qdisc netem")
                and normalized_expected_state in state
            ):
                cleanup = docker_exec(
                    container,
                    "tc", "qdisc", "del", "dev", interface, "root",
                )
                if cleanup.returncode != 0:
                    pytest.fail(
                        f"CRITICAL: failed to remove temporary impairment "
                        f"from {container}:{interface}.\n"
                        f"stdout:\n{cleanup.stdout}\n"
                        f"stderr:\n{cleanup.stderr}"
                    )
            elif not state.startswith("qdisc noqueue"):
                pytest.fail(
                    f"CRITICAL: unexpected qdisc state on "
                    f"{container}:{interface}; refusing to modify it:\n"
                    f"{current.stdout}"
                )

            restored = docker_exec(
                container, "tc", "qdisc", "show", "dev", interface
            )
            if (
                restored.returncode != 0
                or not restored.stdout.strip().startswith("qdisc noqueue")
            ):
                pytest.fail(
                    f"CRITICAL: could not verify interface restoration on "
                    f"{container}:{interface}.\n"
                    f"stdout:\n{restored.stdout}\n"
                    f"stderr:\n{restored.stderr}"
                )

            print(f"Cleanup verified: {container}:{interface} returned to noqueue.")


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("iperf3_udp_tests", []),
    ids=lambda case: case["name"],
)
def test_iperf3_udp_performance(test_case):
    """Validate normal UDP throughput, loss, and jitter."""
    result = run_iperf3_udp(test_case)
    print_udp_result(test_case["name"], result)

    assert result["total_packets"] > 0, "iperf3 reported no received packets."
    assert result["receiver_mbps"] >= test_case["min_receiver_mbps"], (
        f'Expected at least {test_case["min_receiver_mbps"]:.2f} Mbps; '
        f'observed {result["receiver_mbps"]:.3f} Mbps.'
    )
    assert result["loss_percent"] <= test_case["max_loss_percent"], (
        f'Packet loss exceeded {test_case["max_loss_percent"]:.3f}%; '
        f'observed {result["loss_percent"]:.3f}%.'
    )
    assert result["jitter_ms"] <= test_case["max_jitter_ms"], (
        f'Jitter exceeded {test_case["max_jitter_ms"]:.3f} ms; '
        f'observed {result["jitter_ms"]:.3f} ms.'
    )


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("iperf3_udp_impairment_tests", []),
    ids=lambda case: case["name"],
)
def test_iperf3_udp_detects_packet_loss(test_case):
    """Pass when the configured packet-loss impairment is detected."""
    profile = next(
        (
            item for item in LAB_CONFIG.get("iperf3_udp_tests", [])
            if item["name"] == test_case["base_profile"]
        ),
        None,
    )
    assert profile is not None, (
        f'UDP base profile {test_case["base_profile"]!r} was not found.'
    )

    container = (
        f'{LAB_CONFIG["lab"]["container_prefix"]}{profile["client"]}'
    )
    interface = test_case["interface"]
    loss = float(test_case["loss_percent"])
    loss_arg = f"{loss:g}%"

    with temporary_netem(
        container, interface,
        ["loss", loss_arg],
        f"loss {loss_arg}",
    ):
        result = run_iperf3_udp(profile)
        print_udp_result(test_case["name"], result)

        assert result["total_packets"] > 0, (
            "iperf3 reported no received UDP packets."
        )
        assert result["loss_percent"] > test_case["min_observed_loss_percent"], (
            f'Impairment not detected: expected loss above '
            f'{test_case["min_observed_loss_percent"]:.3f}%; '
            f'observed {result["loss_percent"]:.3f}%.'
        )


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("iperf3_udp_jitter_tests", []),
    ids=lambda case: case["name"],
)
def test_iperf3_udp_detects_jitter(test_case):
    """Pass when controlled delay variation produces measurable UDP jitter."""
    profile = next(
        (
            item for item in LAB_CONFIG.get("iperf3_udp_tests", [])
            if item["name"] == test_case["base_profile"]
        ),
        None,
    )
    assert profile is not None, (
        f'UDP base profile {test_case["base_profile"]!r} was not found.'
    )

    container = (
        f'{LAB_CONFIG["lab"]["container_prefix"]}{profile["client"]}'
    )
    interface = test_case["interface"]
    base_delay = test_case["base_delay_ms"]
    variation = test_case["delay_variation_ms"]
    expected_state = f"delay {base_delay}ms {variation}ms"

    with temporary_netem(
        container, interface,
        ["delay", f"{base_delay}ms", f"{variation}ms"],
        expected_state,
    ):
        result = run_iperf3_udp(
            profile, rate_mbps=test_case["target_bitrate_mbps"]
        )
        print_udp_result(test_case["name"], result)

        assert result["total_packets"] > 0, (
            "iperf3 reported no received UDP packets."
        )
        assert result["loss_percent"] <= profile["max_loss_percent"], (
            f'Packet loss exceeded the base profile limit of '
            f'{profile["max_loss_percent"]:.3f}%; '
            f'observed {result["loss_percent"]:.3f}%.'
        )
        assert result["jitter_ms"] >= test_case["min_observed_jitter_ms"], (
            f'Jitter impairment not detected: expected at least '
            f'{test_case["min_observed_jitter_ms"]:.3f} ms; '
            f'observed {result["jitter_ms"]:.3f} ms.'
        )
