"""ICMP latency validation under normal and controlled-delay conditions."""

import re
from pathlib import Path
import subprocess
from src.packet_capture import PacketCapture
import pytest
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "configs" / "lab-expanded.yaml"

with CONFIG_PATH.open(encoding="utf-8") as config_file:
    LAB_CONFIG = yaml.safe_load(config_file)

PING_STATS_PATTERN = re.compile(
    r"(?P<sent>\d+)\s+packets transmitted,\s*"
    r"(?P<received>\d+)\s+packets received,\s*"
    r"(?P<loss>[\d.]+)% packet loss"
)

RTT_PATTERN = re.compile(
    r"round-trip min/avg/max = "
    r"(?P<minimum>[\d.]+)/(?P<average>[\d.]+)/"
    r"(?P<maximum>[\d.]+) ms"
)


def docker_exec(container, *args, timeout=10):
    return subprocess.run(
        ["docker", "exec", container, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def measure_latency(test_case, capture_name=None):
    """Run BusyBox ping and parse packet-loss and RTT statistics."""
    lab = LAB_CONFIG["lab"]
    client_container = f'{lab["container_prefix"]}{test_case["client"]}'
    capture_name = capture_name or test_case["name"]
    output_path = (
        PROJECT_ROOT / "artifacts" / "pcap" / f"{capture_name}.pcap"
    )

    capture = PacketCapture(
        container=client_container,
        interface=test_case.get("interface", "eth1"),
        capture_filter=f'host {test_case["destination"]} and icmp',
        output_path=output_path,
    )
    command = [
        "docker", "exec", client_container,
        "ping",
        "-n",
        "-c", str(test_case["packet_count"]),
        "-i", str(test_case["interval_seconds"]),
        "-w", str(test_case["timeout_seconds"]),
        test_case["destination"],
    ]

    capture.start()
    try:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=test_case["timeout_seconds"] + 5,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(f'{capture_name}: ping timed out: {exc}')
    finally:
        capture.stop()

    assert capture.packet_count > 0, (
        f"{capture_name}: no ICMP packets matched the capture filter. "
        f"PCAP: {output_path}"
    )

    print(
        f"{capture_name}: captured {capture.packet_count} packets; "
        f"PCAP saved to {output_path}"
    )

    output = result.stdout + "\n" + result.stderr
    stats_match = PING_STATS_PATTERN.search(output)
    rtt_match = RTT_PATTERN.search(output)

    if not stats_match or not rtt_match:
        pytest.fail(
            f'{test_case["name"]}: unable to parse ping statistics.\n'
            f"Exit code: {result.returncode}\n"
            f"Output:\n{output}"
        )

    return {
        "sent": int(stats_match.group("sent")),
        "received": int(stats_match.group("received")),
        "loss_percent": float(stats_match.group("loss")),
        "min_rtt_ms": float(rtt_match.group("minimum")),
        "avg_rtt_ms": float(rtt_match.group("average")),
        "max_rtt_ms": float(rtt_match.group("maximum")),
    }


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("latency_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_icmp_latency(test_case):
    """Check normal-path average RTT and packet loss against configured limits."""
    result = measure_latency(test_case)

    print(
        f'{test_case["name"]}: '
        f'RTT min/avg/max={result["min_rtt_ms"]:.3f}/'
        f'{result["avg_rtt_ms"]:.3f}/'
        f'{result["max_rtt_ms"]:.3f} ms, '
        f'loss={result["loss_percent"]:.3f}% '
        f'({result["received"]}/{result["sent"]} replies)'
    )

    assert result["sent"] > 0, "Ping transmitted no packets."
    assert result["received"] > 0, "Ping received no replies."
    assert result["loss_percent"] <= test_case["max_loss_percent"], (
        f'{test_case["name"]}: packet loss was '
        f'{result["loss_percent"]:.3f}%; maximum allowed is '
        f'{test_case["max_loss_percent"]:.3f}%.'
    )
    assert result["avg_rtt_ms"] <= test_case["max_avg_rtt_ms"], (
        f'{test_case["name"]}: average RTT was '
        f'{result["avg_rtt_ms"]:.3f} ms; maximum allowed is '
        f'{test_case["max_avg_rtt_ms"]:.3f} ms.'
    )


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("latency_impairment_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_icmp_latency_detects_added_delay(test_case):
    """Verify added egress delay increases RTT and is removed after testing."""
    base_profile = next(
        (
            profile
            for profile in LAB_CONFIG.get("latency_tests", [])
            if profile["name"] == test_case["base_profile"]
        ),
        None,
    )
    assert base_profile is not None, (
        f'{test_case["name"]}: base profile '
        f'{test_case["base_profile"]!r} was not found.'
    )

    lab = LAB_CONFIG["lab"]
    client_container = f'{lab["container_prefix"]}{base_profile["client"]}'
    interface = base_profile["interface"]
    delay_ms = test_case["delay_ms"]
    impairment_attempted = False

    try:
        initial = docker_exec(
            client_container, "tc", "qdisc", "show", "dev", interface
        )
        assert initial.returncode == 0, (
            f"Cannot inspect initial qdisc: {initial.stderr}"
        )
        assert initial.stdout.strip().startswith("qdisc noqueue"), (
            f"Refusing to overwrite unexpected qdisc on "
            f"{client_container}:{interface}:\n{initial.stdout}"
        )

        # Set before applying so cleanup checks even if application is partial.
        impairment_attempted = True
        apply_result = docker_exec(
            client_container,
            "tc", "qdisc", "replace", "dev", interface,
            "root", "netem", "delay", f"{delay_ms}ms",
        )
        assert apply_result.returncode == 0, (
            f"Failed to apply delay impairment.\n"
            f"stdout:\n{apply_result.stdout}\n"
            f"stderr:\n{apply_result.stderr}"
        )

        result = measure_latency(
            base_profile,
            capture_name=test_case["name"],
        )

        print(
            f'{test_case["name"]}: '
            f'average RTT={result["avg_rtt_ms"]:.3f} ms, '
            f'loss={result["loss_percent"]:.3f}%, '
            f'configured one-way delay={delay_ms} ms'
        )

        assert result["received"] > 0, "Ping received no replies."
        assert result["loss_percent"] <= base_profile["max_loss_percent"], (
            f'Unexpected packet loss under delay impairment: '
            f'{result["loss_percent"]:.3f}%.'
        )
        assert (
            result["avg_rtt_ms"] >= test_case["min_observed_avg_rtt_ms"]
        ), (
            f'Added delay was not detected: average RTT was '
            f'{result["avg_rtt_ms"]:.3f} ms; expected at least '
            f'{test_case["min_observed_avg_rtt_ms"]:.3f} ms.'
        )

    finally:
        if impairment_attempted:
            current = docker_exec(
                client_container, "tc", "qdisc", "show", "dev", interface
            )
            if current.returncode != 0:
                pytest.fail(
                    f"CRITICAL: cannot inspect qdisc on "
                    f"{client_container}:{interface}. Inspect and restore "
                    f"the interface manually before running more tests."
                )

            state = current.stdout.strip()

            if state.startswith("qdisc netem") and f"delay {delay_ms}ms" in state:
                cleanup = docker_exec(
                    client_container,
                    "tc", "qdisc", "del", "dev", interface, "root",
                )
                if cleanup.returncode != 0:
                    pytest.fail(
                        f"CRITICAL: failed to remove temporary delay from "
                        f"{client_container}:{interface}.\n"
                        f"stdout:\n{cleanup.stdout}\n"
                        f"stderr:\n{cleanup.stderr}"
                    )
            elif not state.startswith("qdisc noqueue"):
                pytest.fail(
                    f"CRITICAL: unexpected qdisc state on "
                    f"{client_container}:{interface}; refusing to modify it:\n"
                    f"{current.stdout}"
                )

            restored = docker_exec(
                client_container, "tc", "qdisc", "show", "dev", interface
            )
            if (
                restored.returncode != 0
                or not restored.stdout.strip().startswith("qdisc noqueue")
            ):
                pytest.fail(
                    f"CRITICAL: could not verify interface restoration on "
                    f"{client_container}:{interface}.\n"
                    f"stdout:\n{restored.stdout}\n"
                    f"stderr:\n{restored.stderr}"
                )

            print(
                f"Cleanup verified: {client_container}:{interface} "
                f"returned to noqueue."
            )
