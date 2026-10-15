"""Execute SR Linux CLI commands through Docker."""

import subprocess


class CLIRunnerError(RuntimeError):
    """Raised when a CLI command cannot be executed successfully."""


def _stream_text(value) -> str:
    """Convert captured subprocess output to text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def run_router_cli_command(
    container_name: str,
    command: str,
    timeout: float = 30.0,
) -> str:
    """Execute one SR Linux CLI command and return its output."""

    if not container_name.strip():
        raise ValueError("container_name must not be empty")

    if not command.strip():
        raise ValueError("command must not be empty")

    if "\n" in command or "\r" in command:
        raise ValueError("Only one CLI command may be supplied")

    if timeout <= 0:
        raise ValueError("timeout must be greater than zero")

    try:
        result = subprocess.run(
            [
                "docker",
                "exec",
                "-i",
                container_name,
                "sr_cli",
            ],
            input=f"{command}\nquit\n",
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        partial_output = "\n".join(
            part
            for part in (
                _stream_text(exc.stdout).strip(),
                _stream_text(exc.stderr).strip(),
            )
            if part
        )

        detail = (
            f"\nPartial output:\n{partial_output}"
            if partial_output
            else ""
        )

        raise CLIRunnerError(
            f"CLI command timed out after {timeout:g} seconds.\n"
            f"Router container: {container_name}\n"
            f"Command: {command}{detail}"
        ) from exc

    except OSError as exc:
        raise CLIRunnerError(
            f"Could not execute Docker while running a CLI command.\n"
            f"Router container: {container_name}\n"
            f"Command: {command}\n"
            f"Reason: {exc}"
        ) from exc

    stdout = _stream_text(result.stdout).strip()
    stderr = _stream_text(result.stderr).strip()
    output = "\n".join(part for part in (stdout, stderr) if part)

    if result.returncode != 0:
        raise CLIRunnerError(
            f"CLI execution failed.\n"
            f"Router container: {container_name}\n"
            f"Command: {command}\n"
            f"Exit code: {result.returncode}\n"
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}"
        )

    if "Parsing error:" in output:
        raise CLIRunnerError(
            f"SR Linux CLI reported a parsing error.\n"
            f"Router container: {container_name}\n"
            f"Command: {command}\n"
            f"Output:\n{output}"
        )

    return output
