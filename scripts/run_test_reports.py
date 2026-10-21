"""Run a pytest selection and generate all project quality reports."""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

from src.quality_metrics import build_quality_metrics


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run pytest once and generate JUnit XML, HTML, JSON, "
            "and category-level quality metrics."
        )
    )
    parser.add_argument(
        "--markers",
        required=True,
        help='Pytest marker expression, e.g. "expanded_lab or unit".',
    )
    parser.add_argument(
        "--name",
        required=True,
        help="Report name used as the filename prefix.",
    )
    args = parser.parse_args()

    if not args.markers.strip():
        parser.error("--markers must not be empty.")

    if not REPORT_NAME_PATTERN.fullmatch(args.name):
        parser.error(
            "--name must contain only letters, digits, underscores, "
            "or hyphens, and must start with a letter or digit."
        )

    report_dir = PROJECT_ROOT / "artifacts" / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)

    paths = {
        "junit": report_dir / f"{args.name}.xml",
        "html": report_dir / f"{args.name}.html",
        "json": report_dir / f"{args.name}.json",
        "quality": report_dir / f"{args.name}-quality.json",
    }

    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-m",
        args.markers,
        f"--junitxml={paths['junit']}",
        f"--html={paths['html']}",
        "--self-contained-html",
        "--json-report",
        f"--json-report-file={paths['json']}",
    ]

    print(f"Project root: {PROJECT_ROOT}")
    print(f"Selected markers: {args.markers}")
    print(f"Report name: {args.name}")
    print(f"Running: {shlex.join(command)}", flush=True)

    try:
        result = subprocess.run(command, cwd=PROJECT_ROOT, check=False)
    except OSError as exc:
        print(f"ERROR: unable to start pytest: {exc}", file=sys.stderr)
        return 2

    try:
        with paths["json"].open(encoding="utf-8") as report_file:
            report = json.load(report_file)

        metrics = build_quality_metrics(report)

        with paths["quality"].open("w", encoding="utf-8") as output_file:
            json.dump(metrics, output_file, indent=2, sort_keys=True)
            output_file.write("\n")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            f"ERROR: pytest finished with exit code {result.returncode}, "
            f"but quality metrics could not be generated: {exc}",
            file=sys.stderr,
        )
        return result.returncode or 2

    overall = metrics["overall"]
    print("\n=== Quality summary ===")
    print(
        f"Executed: {overall['executed']}, "
        f"passed: {overall['passed']}, "
        f"failed: {overall['failed']}, "
        f"errors: {overall['errors']}, "
        f"skipped: {overall['skipped']}"
    )
    print(f"Pass rate: {overall['pass_rate_percent']}")
    print(
        "Total pytest duration: "
        f"{overall['reported_duration_seconds']:.3f} seconds"
    )

    print("\n=== Generated reports ===")
    for label, path in paths.items():
        print(f"{label}: {path.relative_to(PROJECT_ROOT)}")

    # Preserve pytest's exit code so a failing test run remains a failure
    # for CI and shell automation, even when reports were generated.
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
