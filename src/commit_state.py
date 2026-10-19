"""Parsing helpers for SR Linux configuration commit state."""

import re


_COMMIT_HEADER = re.compile(r"^\s*commit\s+(\d+)\s*\{\s*$")
_STATUS_LINE = re.compile(r"^\s*status\s+([a-z-]+)\s*$")


def parse_commit_statuses(output: str) -> dict[str, str]:
    """Return configuration commit IDs mapped to their reported statuses.

    Raises ValueError when the output is empty, contains no commit records,
    or contains a commit record without a parseable status.
    """
    if not isinstance(output, str) or not output.strip():
        raise ValueError("Commit-state output is empty")

    lines = output.splitlines()
    headers = [
        (index, match.group(1))
        for index, line in enumerate(lines)
        if (match := _COMMIT_HEADER.match(line))
    ]

    if not headers:
        raise ValueError("No configuration commit records were parsed")

    statuses = {}

    for position, (start, commit_id) in enumerate(headers):
        end = (
            headers[position + 1][0]
            if position + 1 < len(headers)
            else len(lines)
        )

        status_values = [
            match.group(1)
            for line in lines[start + 1:end]
            if (match := _STATUS_LINE.match(line))
        ]

        if len(status_values) != 1:
            raise ValueError(
                f"Commit {commit_id} must have exactly one status field; "
                f"found {len(status_values)}"
            )

        statuses[commit_id] = status_values[0]

    return statuses


def find_new_unconfirmed_commit(
    previous_statuses: dict[str, str],
    current_statuses: dict[str, str],
) -> str:
    """Identify exactly one newly created commit with status unconfirmed."""
    candidates = [
        commit_id
        for commit_id, status in current_statuses.items()
        if commit_id not in previous_statuses and status == "unconfirmed"
    ]

    if len(candidates) != 1:
        raise ValueError(
            "Expected exactly one newly created unconfirmed commit; "
            f"found {len(candidates)}: {candidates}"
        )

    return candidates[0]
