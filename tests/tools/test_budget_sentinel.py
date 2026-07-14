from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tools.budget_sentinel import EXIT_LOW, EXIT_UNAVAILABLE, main, read_snapshot

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


def invoke(path: Path, command: str, *extra: str) -> int:
    return main(["--state-file", str(path), *extra, command], now=NOW)


def test_set_is_atomic_and_records_without_deciding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "0.49"], now=NOW) == 0
    assert read_snapshot(path).amount.as_tuple() == (0, (4, 9), -2)
    assert list(tmp_path.iterdir()) == [path]
    output = capsys.readouterr().out
    assert "recorded=true" in output
    assert "decision=" not in output


def test_equal_threshold_continues(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "0.50"], now=NOW) == 0
    assert invoke(path, "guard") == 0


def test_above_and_below_threshold(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "1.25"], now=NOW) == 0
    assert invoke(path, "guard") == 0
    assert main(["--state-file", str(path), "set", "0.49"], now=NOW) == 0
    assert invoke(path, "status") == EXIT_LOW
    assert "decision=handoff-required" in capsys.readouterr().out


def test_custom_threshold(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "1"], now=NOW) == 0
    assert invoke(path, "guard", "--threshold", "1.01") == EXIT_LOW


@pytest.mark.parametrize("amount", ["nope", "-1", "NaN", "Infinity"])
def test_invalid_amount_fails_closed(tmp_path: Path, amount: str) -> None:
    assert (
        main(["--state-file", str(tmp_path / "budget.json"), "set", amount], now=NOW)
        == EXIT_UNAVAILABLE
    )


def test_missing_and_malformed_snapshot_fail_closed(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert invoke(path, "guard") == EXIT_UNAVAILABLE
    path.write_text("not-json", encoding="utf-8")
    assert invoke(path, "guard") == EXIT_UNAVAILABLE


def test_stale_snapshot_fails_closed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps({"amount_usd": "5", "updated_at": (NOW - timedelta(hours=7)).isoformat()}),
        encoding="utf-8",
    )
    assert invoke(path, "guard") == EXIT_UNAVAILABLE
    assert "decision=snapshot-stale" in capsys.readouterr().out


def test_handoff_prints_protocol_without_mutating_snapshot(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "0.10"], now=NOW) == 0
    before = path.read_bytes()
    assert invoke(path, "handoff") == EXIT_LOW
    assert path.read_bytes() == before
    assert "append HANDOFF-LOG" in capsys.readouterr().out
