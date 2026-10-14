"""Execute SR Linux CLI commands through Docker."""

import subprocess


def run_router_cli_command(
    container_name: str,
    command: str,
    timeout: int = 30,
) -> str:
    """Execute one SR Linux CLI command and return its output."""

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

    output = result.stdout.strip()
    errors = result.stderr.strip()

    if result.returncode != 0:
        raise RuntimeError(
            f"CLI execution failed on {container_name}. "
            f"Exit code: {result.returncode}\n"
            f"stdout:\n{output}\nstderr:\n{errors}"
        )

    if "Parsing error:" in output or "Parsing error:" in errors:
        raise RuntimeError(
            f"SR Linux CLI parsing error on {container_name}.\n"
            f"stdout:\n{output}\nstderr:\n{errors}"
        )

    return "\n".join(part for part in (output, errors) if part)
