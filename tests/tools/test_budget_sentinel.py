from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from tools.budget_sentinel import (
    DEFAULT_BURN_RATE,
    EXIT_LOW,
    EXIT_UNAVAILABLE,
    main,
    read_snapshot,
)

NOW = datetime(2026, 7, 14, 12, tzinfo=UTC)


def invoke(path: Path, command: str, *extra: str, now: datetime = NOW) -> int:
    return main(["--state-file", str(path), *extra, command], now=now)


def test_set_below_threshold_is_atomic_records_and_fails_loud(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "1.49"], now=NOW) == EXIT_LOW
    assert read_snapshot(path).amount.as_tuple() == (0, (1, 4, 9), -2)
    assert list(tmp_path.iterdir()) == [path]
    output = capsys.readouterr().out
    assert "recorded=true" in output
    assert "decision=handoff-required" in output
    assert "append HANDOFF-LOG" in output


def test_set_at_or_above_threshold_records_and_continues(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "5.0"], now=NOW) == 0
    output = capsys.readouterr().out
    assert "recorded=true" in output
    assert "decision=continue" in output


def test_equal_threshold_continues(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "1.50"], now=NOW) == 0
    assert invoke(path, "guard") == 0


def test_above_and_below_threshold(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "2.25"], now=NOW) == 0
    assert invoke(path, "guard") == 0
    assert main(["--state-file", str(path), "set", "1.49"], now=NOW) == EXIT_LOW
    assert invoke(path, "status") == EXIT_LOW
    assert "decision=handoff-required" in capsys.readouterr().out


def test_custom_threshold(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "2"], now=NOW) == 0
    assert invoke(path, "guard", "--threshold", "2.01") == EXIT_LOW


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
    assert main(["--state-file", str(path), "set", "0.10"], now=NOW) == EXIT_LOW
    before = path.read_bytes()
    assert invoke(path, "handoff") == EXIT_LOW
    assert path.read_bytes() == before
    assert "append HANDOFF-LOG" in capsys.readouterr().out


def test_handoff_prints_protocol_even_when_snapshot_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    assert invoke(path, "handoff") == EXIT_UNAVAILABLE
    output = capsys.readouterr().out
    assert "decision=snapshot-unavailable-fail-closed" in output
    assert "append HANDOFF-LOG" in output


def test_handoff_prints_protocol_even_when_snapshot_stale(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps({"amount_usd": "5", "updated_at": (NOW - timedelta(hours=7)).isoformat()}),
        encoding="utf-8",
    )
    assert invoke(path, "handoff") == EXIT_UNAVAILABLE
    output = capsys.readouterr().out
    assert "decision=snapshot-stale" in output
    assert "append HANDOFF-LOG" in output


# --- Time decay: the boundary moves without another `set` ------------------


def test_effective_balance_decays_and_triggers_handoff(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    # Default burn rate is 1.00 USD/h: 5.00 - 4h -> effective 1.00 < 1.50.
    assert main(["--state-file", str(path), "set", "5.0"], now=NOW) == 0
    assert invoke(path, "guard", now=NOW + timedelta(hours=3)) == 0  # 2.00 >= 1.50
    assert invoke(path, "guard", now=NOW + timedelta(hours=4)) == EXIT_LOW
    output = capsys.readouterr().out
    assert "effective_usd=1.00" in output
    assert "decision=handoff-required" in output


def test_effective_balance_never_negative(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "2.0"], now=NOW) == 0
    assert invoke(path, "status", now=NOW + timedelta(hours=5)) == EXIT_LOW
    assert "effective_usd=0.00" in capsys.readouterr().out


def test_burn_rate_auto_calibrates_from_consecutive_sets(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "10"], now=NOW) == 0
    later = NOW + timedelta(hours=1)
    # Spent 2.00 USD in 1h -> calibrated rate 2.00 USD/h.
    assert main(["--state-file", str(path), "set", "8"], now=later) == 0
    snapshot = read_snapshot(path)
    assert snapshot.burn_rate == 2
    # 8.00 - 2.00/h * 3.25h = 1.50 -> continue at the boundary...
    assert invoke(path, "guard", now=later + timedelta(hours=3, minutes=15)) == 0
    # ...and handoff-required just past it.
    assert invoke(path, "guard", now=later + timedelta(hours=3, minutes=16)) == EXIT_LOW


def test_calibration_skipped_when_too_soon_or_no_spend(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "10"], now=NOW) == 0
    # Re-set 30s later: below MIN_CALIBRATION_SECONDS, rate carries forward.
    assert main(["--state-file", str(path), "set", "9"], now=NOW + timedelta(seconds=30)) == 0
    assert read_snapshot(path).burn_rate == DEFAULT_BURN_RATE
    # Top-up (amount increased): no spend to calibrate from, rate unchanged.
    assert main(["--state-file", str(path), "set", "20"], now=NOW + timedelta(hours=1)) == 0
    assert read_snapshot(path).burn_rate == DEFAULT_BURN_RATE


def test_burn_rate_override_on_set_is_stored(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "--burn-rate", "3", "set", "8"], now=NOW) == 0
    assert read_snapshot(path).burn_rate == 3
    # 8 - 3*2 = 2.00 >= 1.50 -> continue; 8 - 3*2.2 = 1.40 -> low.
    assert invoke(path, "guard", now=NOW + timedelta(hours=2)) == 0
    assert invoke(path, "guard", now=NOW + timedelta(hours=2, minutes=12)) == EXIT_LOW


def test_burn_rate_override_on_guard_is_ephemeral(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "set", "5"], now=NOW) == 0
    later = NOW + timedelta(hours=1)
    # Stored rate 1.00 -> effective 4.00 -> continue.
    assert invoke(path, "guard", now=later) == 0
    # Ephemeral override 4.00/h -> effective 1.00 -> low; snapshot untouched.
    assert invoke(path, "guard", "--burn-rate", "4", now=later) == EXIT_LOW
    assert read_snapshot(path).burn_rate == DEFAULT_BURN_RATE


def test_zero_burn_rate_disables_decay(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "--burn-rate", "0", "set", "2"], now=NOW) == 0
    assert invoke(path, "guard", now=NOW + timedelta(hours=5)) == 0


def test_legacy_snapshot_without_burn_rate_still_reads(tmp_path: Path) -> None:
    path = tmp_path / "budget.json"
    path.write_text(
        json.dumps({"amount_usd": "5", "updated_at": NOW.isoformat()}),
        encoding="utf-8",
    )
    snapshot = read_snapshot(path)
    assert snapshot.burn_rate == DEFAULT_BURN_RATE
    assert invoke(path, "guard") == 0


@pytest.mark.parametrize("rate", ["nope", "-1", "NaN", "Infinity"])
def test_invalid_burn_rate_fails_closed(tmp_path: Path, rate: str) -> None:
    path = tmp_path / "budget.json"
    assert main(["--state-file", str(path), "--burn-rate", rate, "set", "5"], now=NOW) == (
        EXIT_UNAVAILABLE
    )
