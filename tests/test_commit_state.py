"""Unit tests for SR Linux configuration commit-state parsing."""

import pytest

from src.commit_state import parse_commit_statuses
pytestmark = pytest.mark.unit

@pytest.mark.unit
def test_parse_multiple_commit_statuses():
    output = """
commit 1 {
    type shared
    name default
    status complete
    username root
}
commit 2 {
    type shared
    name default
    status unconfirmed
    username root
}
commit 3 {
    type shared
    name default
    status reverting
    username root
}
"""

    assert parse_commit_statuses(output) == {
        "1": "complete",
        "2": "unconfirmed",
        "3": "reverting",
    }


@pytest.mark.unit
@pytest.mark.parametrize(
    "output",
    ["", "   ", "no commit records here"],
)
def test_reject_empty_or_unrecognized_commit_state(output):
    with pytest.raises(ValueError):
        parse_commit_statuses(output)


@pytest.mark.unit
def test_reject_commit_without_status():
    output = """
commit 12 {
    type shared
    name default
}
"""

    with pytest.raises(ValueError, match="exactly one status"):
        parse_commit_statuses(output)


@pytest.mark.unit
def test_identify_new_unconfirmed_commit():
    from src.commit_state import find_new_unconfirmed_commit

    before = {"1": "complete", "2": "complete"}
    after = {
        "1": "complete",
        "2": "complete",
        "3": "complete",
        "4": "unconfirmed",
    }

    assert find_new_unconfirmed_commit(before, after) == "4"


@pytest.mark.unit
@pytest.mark.parametrize(
    "after",
    [
        {"1": "complete", "2": "complete"},
        {
            "1": "complete",
            "2": "complete",
            "3": "unconfirmed",
            "4": "unconfirmed",
        },
    ],
)
def test_reject_missing_or_ambiguous_new_unconfirmed_commit(after):
    from src.commit_state import find_new_unconfirmed_commit

    before = {"1": "complete", "2": "complete"}

    with pytest.raises(
        ValueError,
        match="Expected exactly one newly created unconfirmed commit",
    ):
        find_new_unconfirmed_commit(before, after)
