"""Behavior tests for the public API of cost_per_request."""

from __future__ import annotations

import pytest

import cost_per_request


def test_normalize_trims_and_lowercases() -> None:
    assert cost_per_request.normalize("  Hello World ") == "hello world"


@pytest.mark.parametrize("value", ["", "   ", "\t\n"])
def test_normalize_rejects_blank_input(value: str) -> None:
    with pytest.raises(ValueError, match="must not be empty"):
        cost_per_request.normalize(value)


def test_version_is_semver() -> None:
    parts = cost_per_request.__version__.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)
