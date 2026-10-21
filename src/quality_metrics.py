"""Calculate quality metrics from pytest-json-report data."""

from collections import Counter
from collections.abc import Mapping
from math import isfinite
from typing import Any


REPORT_CATEGORIES = (
    "unit",
    "integration",
    "expanded_lab",
)

TEST_PHASES = ("setup", "call", "teardown")


def _number(value: Any, field: str) -> float:
    """Convert a report value to a valid, non-negative number."""
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Invalid numeric value for {field}: {value!r}"
        ) from exc

    if not isfinite(result) or result < 0:
        raise ValueError(
            f"Invalid non-negative value for {field}: {value!r}"
        )

    return result


def _test_duration(test: Mapping[str, Any]) -> float:
    """Sum setup, call, and teardown durations for one test."""
    total = 0.0

    for phase in TEST_PHASES:
        details = test.get(phase, {})
        if not isinstance(details, Mapping):
            continue

        total += _number(
            details.get("duration", 0.0),
            f"{test.get('nodeid', '<unknown test>')}.{phase}.duration",
        )

    return total


def _keywords(test: Mapping[str, Any]) -> set[str]:
    """Return a test's pytest keywords as a set of strings."""
    raw = test.get("keywords", [])

    if isinstance(raw, str):
        return {raw}

    if isinstance(raw, (list, tuple, set)):
        return {str(item) for item in raw}

    return set()


def _failure_detail(
    test: Mapping[str, Any],
) -> dict[str, str] | None:
    """Extract a concise failure reason from a test record."""
    outcome = str(test.get("outcome", "unknown")).lower()

    if outcome not in {"failed", "error"}:
        return None

    failed_phase = "unknown"
    phase_details: Mapping[str, Any] = {}

    for phase in TEST_PHASES:
        details = test.get(phase, {})
        if not isinstance(details, Mapping):
            continue

        if details.get("outcome") in {"failed", "error"}:
            failed_phase = phase
            phase_details = details
            break

    crash = phase_details.get("crash", {})
    crash_message = (
        crash.get("message")
        if isinstance(crash, Mapping)
        else None
    )
    reason = crash_message or phase_details.get("longrepr")

    if not reason:
        reason = "Failure reported, but no detailed reason was available."

    return {
        "nodeid": str(test.get("nodeid", "<unknown test>")),
        "phase": failed_phase,
        "reason": str(reason),
    }


def _summarize_tests(
    tests: list[Mapping[str, Any]],
) -> dict[str, Any]:
    """Summarize outcomes and phase timings for a group of tests."""
    outcomes = Counter(
        str(test.get("outcome", "unknown")).lower()
        for test in tests
    )

    passed = outcomes.get("passed", 0)
    failed = outcomes.get("failed", 0)
    errors = outcomes.get("error", 0)
    skipped = outcomes.get("skipped", 0)
    other = len(tests) - passed - failed - errors - skipped

    durations = [_test_duration(test) for test in tests]
    total_duration = sum(durations)
    evaluated = passed + failed + errors

    return {
        "test_count": len(tests),
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "other": other,
        "pass_rate_percent": (
            round(passed / evaluated * 100, 2)
            if evaluated
            else None
        ),
        "total_phase_duration_seconds": round(total_duration, 6),
        "average_phase_duration_seconds": (
            round(total_duration / len(tests), 6)
            if tests
            else 0.0
        ),
    }


def build_quality_metrics(
    report: Mapping[str, Any],
) -> dict[str, Any]:
    """Build overall and pytest-marker metrics from JSON report data.

    Category counts may overlap when tests have multiple markers.
    Pass rate is passed / (passed + failed + errors); skipped tests
    are excluded from this denominator.
    """
    if not isinstance(report, Mapping):
        raise ValueError("The pytest JSON report must be a JSON object.")

    raw_tests = report.get("tests")
    if not isinstance(raw_tests, list):
        raise ValueError("The pytest JSON report must contain a tests list.")

    tests: list[Mapping[str, Any]] = []
    for index, test in enumerate(raw_tests):
        if not isinstance(test, Mapping):
            raise ValueError(f"Test record {index} must be a JSON object.")
        tests.append(test)

    raw_summary = report.get("summary", {})
    summary = raw_summary if isinstance(raw_summary, Mapping) else {}

    overall = _summarize_tests(tests)
    overall.update({
        "collected": int(summary.get("collected", len(tests))),
        "executed": len(tests),
        "deselected": int(summary.get("deselected", 0)),
        "reported_duration_seconds": round(
            _number(report.get("duration", 0.0), "duration"),
            6,
        ),
        "failure_details": [
            detail
            for test in tests
            if (detail := _failure_detail(test)) is not None
        ],
    })

    categories: dict[str, Any] = {}

    for category in REPORT_CATEGORIES:
        matching = [
            test
            for test in tests
            if category in _keywords(test)
        ]

        category_summary = _summarize_tests(matching)
        category_summary["failure_details"] = [
            detail
            for test in matching
            if (detail := _failure_detail(test)) is not None
        ]
        categories[category] = category_summary

    return {
        "schema_version": 1,
        "overall": overall,
        "categories": categories,
    }
