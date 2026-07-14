"""Operator-maintained budget guard for deterministic continuity handoffs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

DEFAULT_STATE = Path(".continuity-budget.json")
DEFAULT_THRESHOLD = Decimal("0.50")
DEFAULT_MAX_AGE_HOURS = Decimal("6")
EXIT_LOW = 20
EXIT_UNAVAILABLE = 21


@dataclass(frozen=True)
class Snapshot:
    amount: Decimal
    updated_at: datetime


def parse_nonnegative(value: str, label: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ValueError(f"{label} must be a decimal number") from error
    if not parsed.is_finite() or parsed < 0:
        raise ValueError(f"{label} must be a finite non-negative number")
    return parsed


def write_snapshot(path: Path, amount: Decimal, now: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (
        json.dumps(
            {"amount_usd": str(amount), "updated_at": now.astimezone(UTC).isoformat()},
            indent=2,
        )
        + "\n"
    )
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def read_snapshot(path: Path) -> Snapshot:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        amount = parse_nonnegative(str(payload["amount_usd"]), "stored amount")
        updated_at = datetime.fromisoformat(str(payload["updated_at"]))
        if updated_at.tzinfo is None:
            raise ValueError("stored timestamp must include a timezone")
    except (OSError, KeyError, TypeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"budget snapshot unavailable: {error}") from error
    return Snapshot(amount=amount, updated_at=updated_at.astimezone(UTC))


def evaluate(
    snapshot: Snapshot, threshold: Decimal, max_age_hours: Decimal, now: datetime
) -> tuple[int, str]:
    age_seconds = Decimal(str((now.astimezone(UTC) - snapshot.updated_at).total_seconds()))
    if age_seconds < 0 or age_seconds > max_age_hours * Decimal("3600"):
        return EXIT_UNAVAILABLE, "snapshot-stale"
    if snapshot.amount < threshold:
        return EXIT_LOW, "handoff-required"
    return 0, "continue"


def print_status(
    snapshot: Snapshot, threshold: Decimal, max_age_hours: Decimal, now: datetime
) -> int:
    code, decision = evaluate(snapshot, threshold, max_age_hours, now)
    print(f"balance_usd={snapshot.amount}")
    print(f"threshold_usd={threshold}")
    print(f"updated_at={snapshot.updated_at.isoformat()}")
    print(f"decision={decision}")
    return code


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Check an operator-entered budget snapshot; this is not a Vercel billing API."
    )
    result.add_argument("--state-file", type=Path, default=DEFAULT_STATE)
    result.add_argument("--threshold", default=str(DEFAULT_THRESHOLD))
    result.add_argument("--max-age-hours", default=str(DEFAULT_MAX_AGE_HOURS))
    commands = result.add_subparsers(dest="command", required=True)
    set_command = commands.add_parser(
        "set", help="atomically record an operator-reported USD balance"
    )
    set_command.add_argument("amount")
    commands.add_parser("status", help="show the current decision")
    commands.add_parser("guard", help="fail closed when work should not continue")
    commands.add_parser("handoff", help="print the required graceful-handoff sequence")
    return result


def main(argv: Sequence[str] | None = None, *, now: datetime | None = None) -> int:
    args = parser().parse_args(argv)
    current_time = now or datetime.now(UTC)
    try:
        threshold = parse_nonnegative(args.threshold, "threshold")
        max_age = parse_nonnegative(args.max_age_hours, "max age")
        if max_age == 0:
            raise ValueError("max age must be greater than zero")
        if args.command == "set":
            amount = parse_nonnegative(args.amount, "amount")
            write_snapshot(args.state_file, amount, current_time)
            print(f"balance_usd={amount}")
            print(f"updated_at={current_time.astimezone(UTC).isoformat()}")
            print("recorded=true")
            return 0
        snapshot = read_snapshot(args.state_file)
    except ValueError as error:
        print(f"error={error}", file=sys.stderr)
        print("action=run: python tools/budget_sentinel.py set <amount>", file=sys.stderr)
        return EXIT_UNAVAILABLE

    code = print_status(snapshot, threshold, max_age, current_time)
    if args.command == "handoff":
        print(
            "handoff=finish smallest safe step; append HANDOFF-LOG; update STATE; "
            "commit; set CHECKPOINT IDLE; stop"
        )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
