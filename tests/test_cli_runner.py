"""Unit tests for the SR Linux CLI runner."""

import subprocess
from types import SimpleNamespace

import pytest

from src.cli_runner import (
    CLIRunnerError,
    run_router_cli_command,
    run_router_cli_commands,
)
pytestmark = pytest.mark.unit

@pytest.mark.unit
def test_successful_command_returns_output(monkeypatch):
    def fake_run(*args, **kwargs):
        assert args[0] == [
            "docker", "exec", "-i", "clab-srl-lab-R1", "sr_cli"
        ]
        assert kwargs["input"] == "show interface\nquit\n"
        return SimpleNamespace(
            returncode=0,
            stdout="ethernet-1/1 is up\n",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    output = run_router_cli_command(
        "clab-srl-lab-R1",
        "show interface",
    )

    assert output == "ethernet-1/1 is up"


@pytest.mark.unit
def test_nonzero_exit_includes_execution_details(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout="command output",
            stderr="container error",
        ),
    )

    with pytest.raises(CLIRunnerError) as exc:
        run_router_cli_command("clab-srl-lab-R1", "show interface")

    message = str(exc.value)
    assert "clab-srl-lab-R1" in message
    assert "show interface" in message
    assert "container error" in message
    assert "Exit code: 1" in message


@pytest.mark.unit
def test_cli_parsing_error_is_reported(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="Parsing error: unknown token",
            stderr="",
        ),
    )

    with pytest.raises(CLIRunnerError, match="parsing error"):
        run_router_cli_command("clab-srl-lab-R1", "invalid command")


@pytest.mark.unit
def test_timeout_includes_router_and_command(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=2,
            output=b"partial output",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CLIRunnerError) as exc:
        run_router_cli_command(
            "clab-srl-lab-R1",
            "show interface",
            timeout=2,
        )

    message = str(exc.value)
    assert "timed out" in message
    assert "clab-srl-lab-R1" in message
    assert "show interface" in message
    assert "partial output" in message


@pytest.mark.unit
def test_missing_docker_executable_is_reported(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("docker executable not found")

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(CLIRunnerError, match="Could not execute Docker"):
        run_router_cli_command("clab-srl-lab-R1", "show interface")


@pytest.mark.unit
def test_multiline_command_is_rejected():
    with pytest.raises(ValueError, match="Only one CLI command"):
        run_router_cli_command(
            "clab-srl-lab-R1",
            "show interface\nshow version",
        )


@pytest.mark.unit
def test_nonpositive_timeout_is_rejected():
    with pytest.raises(ValueError, match="timeout must be greater than zero"):
        run_router_cli_command(
            "clab-srl-lab-R1",
            "show interface",
            timeout=0,
        )


@pytest.mark.unit
def test_nonzero_exit_can_return_expected_network_failure(monkeypatch):
    ping_output = (
        "PING 192.0.2.1 (192.0.2.1) 56(84) bytes of data.\n"
        "--- 192.0.2.1 ping statistics ---\n"
        "3 packets transmitted, 0 received, 100% packet loss"
    )

    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=1,
            stdout=ping_output,
            stderr="",
        ),
    )

    output = run_router_cli_command(
        "clab-srl-lab-R1",
        "ping 192.0.2.1 network-instance default -c 3",
        check_returncode=False,
    )

    assert "3 packets transmitted, 0 received" in output
    assert "100% packet loss" in output


@pytest.mark.unit
def test_multiple_commands_run_in_one_session(monkeypatch):
    def fake_run(args, **kwargs):
        assert args == [
            "docker", "exec", "-i", "clab-srl-lab-R1", "sr_cli"
        ]
        assert kwargs["input"] == (
            "show version\n"
            "show interface\n"
            "quit\n"
        )

        return SimpleNamespace(
            returncode=0,
            stdout="SR Linux version\nethernet-1/1 is up",
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    output = run_router_cli_commands(
        "clab-srl-lab-R1",
        ["show version", "show interface"],
    )

    assert "SR Linux version" in output
    assert "ethernet-1/1 is up" in output
