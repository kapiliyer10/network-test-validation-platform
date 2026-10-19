"""Reusable tcpdump capture lifecycle for Docker-hosted Linux endpoints."""

from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid


class PacketCaptureError(RuntimeError):
    """Raised when packet capture cannot start, stop, or be saved."""


class PacketCapture:
    """Capture filtered traffic inside a container and save a host-side PCAP."""

    def __init__(
        self,
        container: str,
        interface: str,
        capture_filter: str,
        output_path: Path,
        startup_timeout: float = 3.0,
    ):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", container):
            raise ValueError("Invalid Docker container name")
        if not re.fullmatch(r"[A-Za-z0-9_.:-]+", interface):
            raise ValueError("Invalid network interface name")
        if not capture_filter.strip():
            raise ValueError("capture_filter must not be empty")
        if startup_timeout <= 0:
            raise ValueError("startup_timeout must be positive")

        self.container = container
        self.interface = interface
        self.capture_filter = capture_filter
        self.output_path = Path(output_path)
        self.startup_timeout = startup_timeout

        token = uuid.uuid4().hex
        self.remote_prefix = f"/tmp/network-test-capture-{token}"
        self.remote_pcap = f"{self.remote_prefix}.pcap"
        self.remote_pid = f"{self.remote_prefix}.pid"
        self.remote_log = f"{self.remote_prefix}.log"

        self.started = False
        self.packet_count = 0

    @staticmethod
    def _run(command: list[str], timeout: float = 15.0):
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PacketCaptureError(
                f"Command failed: {command!r}\n{type(exc).__name__}: {exc}"
            ) from exc

        if result.returncode != 0:
            raise PacketCaptureError(
                f"Command returned {result.returncode}: {command!r}\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )

        return result

    def _cleanup_remote(self) -> None:
        command = [
            "docker", "exec", self.container, "sh", "-c",
            "rm -f "
            + " ".join(
                shlex.quote(path)
                for path in (
                    self.remote_pcap,
                    self.remote_pid,
                    self.remote_log,
                )
            ),
        ]
        try:
            subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass

    def _read_remote_log(self) -> str:
        result = subprocess.run(
            [
                "docker", "exec", self.container,
                "sh", "-c",
                f"cat {shlex.quote(self.remote_log)} 2>/dev/null || true",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return "\n".join(
            part.strip() for part in (result.stdout, result.stderr) if part.strip()
        )

    def start(self) -> None:
        """Start tcpdump and confirm its process is alive."""
        if self.started:
            raise PacketCaptureError("Capture is already running")

        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        capture_args = [
            "tcpdump",
            "-i", self.interface,
            "-nn",
            "-s", "0",
            "-U",
            "-w", self.remote_pcap,
            self.capture_filter,
        ]
        shell_command = (
            f"{shlex.join(capture_args)} "
            f"> {shlex.quote(self.remote_log)} 2>&1 & "
            'capture_pid=$!; '
            f'echo "$capture_pid" > {shlex.quote(self.remote_pid)}'
        )

        # Match the working manual procedure: let the shell launch tcpdump
        # in the background, save its PID, and then exit the Docker exec.
        self._run(
            [
                "docker", "exec", self.container,
                "sh", "-c", shell_command,
            ],
            timeout=10,
        )

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            try:
                status = subprocess.run(
                    [
                        "docker", "exec", self.container, "sh", "-c",
                        f"test -s {shlex.quote(self.remote_pid)} && "
                        f'kill -0 "$(cat {shlex.quote(self.remote_pid)})"',
                    ],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )

                if status.returncode == 0:
                    log = self._read_remote_log()
                    ready_pattern = (
                        rf"listening on\s+{re.escape(self.interface)}"
                    )
                    if re.search(ready_pattern, log, re.IGNORECASE):
                        self.started = True
                        return

            except (OSError, subprocess.TimeoutExpired):
                pass

            time.sleep(0.1)

        log = self._read_remote_log()
        self._cleanup_remote()
        raise PacketCaptureError(
            f"tcpdump did not start in {self.container} on {self.interface}."
            + (f"\nCapture log:\n{log}" if log else "")
        )

    def stop(self) -> None:
        """Stop tcpdump, save the PCAP locally, and validate captured packets."""
        if not self.started:
            return

        capture_finalized = False
        try:
            # Match the successful manual capture: allow traffic to drain,
            # interrupt tcpdump, and give it time to finalize the PCAP.
            time.sleep(1.0)
            stop_command = (
                "killall -INT tcpdump 2>/dev/null || true; "
                "sleep 1"
            )
            self._run(
                [
                    "docker", "exec", self.container,
                    "sh", "-c", stop_command,
                ],
                timeout=10,
            )

            self._run(
                [
                    "docker", "cp",
                    f"{self.container}:{self.remote_pcap}",
                    str(self.output_path),
                ],
                timeout=15,
            )

            size = (
                self.output_path.stat().st_size
                if self.output_path.is_file()
                else 0
            )
            if size <= 24:
                log = self._read_remote_log()
                raise PacketCaptureError(
                    f"PCAP contains no packet records: {self.output_path} "
                    f"({size} bytes). Remote capture files have been preserved "
                    f"with prefix {self.remote_prefix}.\n"
                    f"Capture log:\n{log or '(empty)'}"
                )

            inspection = self._run(
                [
                    "docker", "exec", self.container,
                    "tcpdump", "-nn", "-tttt", "-r", self.remote_pcap,
                ],
                timeout=15,
            )

            packet_lines = [
                line for line in inspection.stdout.splitlines()
                if line.strip()
                and not line.lstrip().startswith("reading from file")
            ]
            self.packet_count = len(packet_lines)

            if self.packet_count == 0:
                log = self._read_remote_log()
                raise PacketCaptureError(
                    f"PCAP contains no decoded packets: {self.output_path}. "
                    f"Remote capture files have been preserved with prefix "
                    f"{self.remote_prefix}.\nCapture log:\n{log or '(empty)'}"
                )

            capture_finalized = True

        finally:
            self.started = False
            # Keep remote evidence if validation failed so the cause can be
            # diagnosed. Remove remote temporary files only after success.
            if capture_finalized:
                self._cleanup_remote()
