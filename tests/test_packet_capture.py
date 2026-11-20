"""Unit tests for process-specific packet-capture shutdown."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.packet_capture import PacketCapture, PacketCaptureError


pytestmark = pytest.mark.unit


def make_capture(tmp_path):
    return PacketCapture(
        container="clab-srl-expanded-H1",
        interface="eth1",
        capture_filter="host 10.0.24.2 and tcp port 18080",
        output_path=tmp_path / "capture.pcap",
    )


def test_stop_signals_only_the_recorded_capture_process(monkeypatch, tmp_path):
    capture = make_capture(tmp_path)
    capture.started = True
    commands = []

    def fake_run(command, timeout=15.0):
        commands.append(command)

        if command[:2] == ["docker", "cp"]:
            Path(command[-1]).write_bytes(b"x" * 64)
            return SimpleNamespace(stdout="", stderr="", returncode=0)

        if command[:3] == ["docker", "exec", capture.container]:
            if "tcpdump" in command:
                return SimpleNamespace(
                    stdout=(
                        "12:00:00.000000 IP 10.0.14.2.12345 > "
                        "10.0.24.2.18080: Flags [S]\n"
                    ),
                    stderr="",
                    returncode=0,
                )

        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(capture, "_run", fake_run)
    monkeypatch.setattr(capture, "_cleanup_remote", lambda: None)
    monkeypatch.setattr("src.packet_capture.time.sleep", lambda _seconds: None)

    capture.stop()

    stop_command = commands[0][-1]
    assert f"pid_file={capture.remote_pid}" in stop_command
    assert 'kill -INT "$capture_pid"' in stop_command
    assert 'kill -0 "$capture_pid"' in stop_command
    assert "killall" not in stop_command
    assert capture.packet_count == 1
    assert capture.started is False
    assert capture.output_path.is_file()


def test_stop_preserves_capture_when_recorded_pid_is_missing(
    monkeypatch, tmp_path
):
    capture = make_capture(tmp_path)
    capture.started = True
    cleanup_called = False

    class MissingPid:
        @staticmethod
        def run(command, timeout=15.0):
            return SimpleNamespace(
                stdout="",
                stderr="Capture PID file is missing",
                returncode=1,
            )

    def fail_cleanup():
        nonlocal cleanup_called
        cleanup_called = True

    monkeypatch.setattr(capture, "_run", MissingPid.run)
    monkeypatch.setattr(capture, "_cleanup_remote", fail_cleanup)
    monkeypatch.setattr("src.packet_capture.time.sleep", lambda _seconds: None)

    with pytest.raises(PacketCaptureError, match="Capture PID file is missing"):
        capture.stop()

    assert capture.started is False
    assert cleanup_called is False


def test_stop_is_a_noop_when_capture_was_not_started(tmp_path):
    capture = make_capture(tmp_path)

    capture.stop()

    assert capture.started is False
    assert capture.packet_count == 0
    assert not capture.output_path.exists()
