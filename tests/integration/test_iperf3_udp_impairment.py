"""Negative UDP performance test with controlled packet loss."""

import json
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


@pytest.mark.expanded_lab
@pytest.mark.integration
@pytest.mark.parametrize(
    "test_case",
    LAB_CONFIG.get("iperf3_udp_impairment_tests", []),
    ids=lambda test_case: test_case["name"],
)
def test_iperf3_udp_detects_packet_loss(test_case):
    lab = LAB_CONFIG["lab"]
    prefix = lab["container_prefix"]

    base_profile = next(
        (
            profile
            for profile in LAB_CONFIG.get("iperf3_udp_tests", [])
            if profile["name"] == test_case["base_profile"]
        ),
        None,
    )
    assert base_profile is not None, (
        f'{test_case["name"]}: base profile '
        f'{test_case["base_profile"]!r} was not found.'
    )

    client_container = f'{prefix}{base_profile["client"]}'
    server_container = f'{prefix}{base_profile["server"]}'
    interface = test_case["interface"]
    impairment_attempted = False

    try:
        # Only proceed if the interface is in its expected original state.
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

        # Set the flag first so cleanup also checks for a partial application.
        impairment_attempted = True
        apply_result = docker_exec(
            client_container,
            "tc", "qdisc", "replace", "dev", interface,
            "root", "netem", "loss", f'{test_case["loss_percent"]}%',
        )
        assert apply_result.returncode == 0, (
            f"Failed to apply impairment.\n"
            f"stdout:\n{apply_result.stdout}\n"
            f"stderr:\n{apply_result.stderr}"
        )

        command = [
            "docker", "exec", client_container,
            "iperf3",
            "-c", base_profile["destination"],
            "-p", str(base_profile["port"]),
            "-u",
            "-b", f'{base_profile["target_bitrate_mbps"]}M',
            "-t", str(base_profile["duration_seconds"]),
            "-i", str(base_profile["interval_seconds"]),
            "-J",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=base_profile["duration_seconds"] + 30,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            pytest.fail(f'{test_case["name"]}: iperf3 timed out: {exc}')

        assert result.returncode == 0, (
            f'{test_case["name"]}: iperf3 failed.\n'
            f"Client: {client_container}; server: {server_container}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )

        try:
            report = json.loads(result.stdout)
            received = report["end"]["sum_received"]
            receiver_mbps = float(received["bits_per_second"]) / 1_000_000
            jitter_ms = float(received["jitter_ms"])
            lost_packets = int(received["lost_packets"])
            total_packets = int(received["packets"])
            loss_percent = float(received["lost_percent"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            pytest.fail(f'{test_case["name"]}: invalid iperf3 JSON: {exc}')

        print(
            f'{test_case["name"]}: '
            f'receiver={receiver_mbps:.3f} Mbps, '
            f'loss={loss_percent:.3f}% '
            f'({lost_packets}/{total_packets} packets), '
            f'jitter={jitter_ms:.3f} ms, '
            f'configured_loss={test_case["loss_percent"]:.3f}%'
        )

        assert total_packets > 0, "iperf3 reported no UDP packets."
        assert loss_percent > test_case["min_observed_loss_percent"], (
            f'Impairment not detected: expected loss above '
            f'{test_case["min_observed_loss_percent"]:.3f}%, '
            f'observed {loss_percent:.3f}%.'
        )

    finally:
        if impairment_attempted:
            # Inspect current state before cleanup so we don't delete an
            # unexpected qdisc that was not created by this test.
            current = docker_exec(
                client_container, "tc", "qdisc", "show", "dev", interface
            )
            if current.returncode != 0:
                pytest.fail(
                    f"CRITICAL: cannot inspect qdisc on "
                    f"{client_container}:{interface}. Inspect and restore "
                    f"the interface manually before running more tests."
                )

            current_state = current.stdout.strip()

            if current_state.startswith("qdisc netem"):
                cleanup = docker_exec(
                    client_container,
                    "tc", "qdisc", "del", "dev", interface, "root",
                )
                if cleanup.returncode != 0:
                    pytest.fail(
                        f"CRITICAL: failed to remove temporary impairment "
                        f"from {client_container}:{interface}.\n"
                        f"stdout:\n{cleanup.stdout}\n"
                        f"stderr:\n{cleanup.stderr}\n"
                        f"Restore the interface before running more tests."
                    )
            elif not current_state.startswith("qdisc noqueue"):
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
                    f"stdout:\n{restored.stdout}\nstderr:\n{restored.stderr}"
                )

            print(
                f"Cleanup verified: {client_container}:{interface} "
                f"returned to noqueue."
            )
