"""Unit tests for pytest JSON quality-metrics calculations."""

import pytest

from src.quality_metrics import build_quality_metrics


pytestmark = pytest.mark.unit


def phase(duration, outcome="passed", **extra):
    return {"duration": duration, "outcome": outcome, **extra}


@pytest.fixture
def sample_report():
    return {
        "duration": 0.75,
        "summary": {"collected": 5, "deselected": 2},
        "tests": [
            {
                "nodeid": "tests/test_example.py::test_unit_pass",
                "keywords": ["unit"],
                "outcome": "passed",
                "setup": phase(0.10),
                "call": phase(0.20),
                "teardown": phase(0.05),
            },
            {
                "nodeid": "tests/integration/test_example.py::test_failure",
                "keywords": ["integration", "expanded_lab"],
                "outcome": "failed",
                "setup": phase(0.01),
                "call": phase(
                    0.30,
                    "failed",
                    crash={"message": "AssertionError: target did not respond"},
                    longrepr="Example traceback",
                ),
                "teardown": phase(0.02),
            },
            {
                "nodeid": "tests/test_example.py::test_skipped",
                "keywords": ["expanded_lab"],
                "outcome": "skipped",
                "setup": phase(0.02),
                "call": phase(0.0, "skipped"),
                "teardown": phase(0.01),
            },
        ],
    }


def test_overall_counts_pass_rate_and_duration(sample_report):
    metrics = build_quality_metrics(sample_report)
    overall = metrics["overall"]

    assert overall["collected"] == 5
    assert overall["deselected"] == 2
    assert overall["executed"] == 3
    assert overall["test_count"] == 3
    assert overall["passed"] == 1
    assert overall["failed"] == 1
    assert overall["errors"] == 0
    assert overall["skipped"] == 1
    assert overall["pass_rate_percent"] == 50.0
    assert overall["total_phase_duration_seconds"] == 0.71
    assert overall["reported_duration_seconds"] == 0.75


def test_category_metrics_and_overlapping_markers(sample_report):
    categories = build_quality_metrics(sample_report)["categories"]

    assert categories["unit"]["test_count"] == 1
    assert categories["unit"]["passed"] == 1
    assert categories["unit"]["pass_rate_percent"] == 100.0
    assert categories["unit"]["total_phase_duration_seconds"] == 0.35

    assert categories["integration"]["test_count"] == 1
    assert categories["integration"]["failed"] == 1
    assert categories["expanded_lab"]["test_count"] == 2
    assert categories["expanded_lab"]["failed"] == 1
    assert categories["expanded_lab"]["skipped"] == 1
    assert categories["expanded_lab"]["pass_rate_percent"] == 0.0


def test_failure_detail_preserves_test_phase_and_reason(sample_report):
    metrics = build_quality_metrics(sample_report)
    failure = metrics["overall"]["failure_details"][0]

    assert failure["nodeid"] == (
        "tests/integration/test_example.py::test_failure"
    )
    assert failure["phase"] == "call"
    assert "AssertionError: target did not respond" in failure["reason"]


def test_empty_report_has_zero_counts_and_no_pass_rate():
    metrics = build_quality_metrics({
        "duration": 0,
        "summary": {"collected": 0, "deselected": 0},
        "tests": [],
    })

    assert metrics["overall"]["test_count"] == 0
    assert metrics["overall"]["pass_rate_percent"] is None
    assert metrics["overall"]["average_phase_duration_seconds"] == 0.0
    assert metrics["categories"]["unit"]["test_count"] == 0


def test_report_without_tests_list_is_rejected():
    with pytest.raises(ValueError, match="tests list"):
        build_quality_metrics({"summary": {}})


def test_negative_test_duration_is_rejected():
    report = {
        "tests": [
            {
                "nodeid": "test_bad_duration",
                "outcome": "passed",
                "setup": phase(-1.0),
            }
        ]
    }

    with pytest.raises(ValueError, match="non-negative"):
        build_quality_metrics(report)
