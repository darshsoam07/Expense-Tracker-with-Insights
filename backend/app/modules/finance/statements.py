"""Bounded UTF-8 statement format for the simulated rail."""

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.core.errors import AppError

COLUMNS = (
    "provider_reference",
    "external_reference",
    "amount",
    "currency",
    "transaction_date",
    "settlement_date",
    "direction",
    "status",
)
MAX_BYTES = 256 * 1024
MAX_ROWS = 500


@dataclass(frozen=True)
class StatementLine:
    provider_reference: str
    external_reference: str
    amount: Decimal
    currency: str
    transaction_date: date
    settlement_date: date
    direction: str
    status: str


def parse_statement(content: bytes) -> list[StatementLine]:
    if len(content) > MAX_BYTES:
        raise AppError(413, "statement_too_large", "Statement exceeds 256 KiB.")
    lines: list[StatementLine] = []
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig"), newline=""), strict=True)
        if tuple(next(reader, [])) != COLUMNS:
            raise ValueError("Unexpected columns")
        for row in reader:
            if len(lines) >= MAX_ROWS:
                raise ValueError("Too many rows")
            provider, external, amount, currency, transaction, settlement, direction, status = row
            if not all(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", ref)
                for ref in (provider, external)
            ):
                raise ValueError("Invalid reference")
            if (
                not re.fullmatch(r"(0|[1-9][0-9]{0,15})(\.[0-9]{1,2})?", amount)
                or Decimal(amount) <= 0
            ):
                raise ValueError("Invalid amount")
            if not re.fullmatch(r"[A-Z]{3}", currency):
                raise ValueError("Invalid currency")
            if direction not in {"outbound", "inbound"} or status not in {"settled", "failed"}:
                raise ValueError("Invalid direction or status")
            dates = [date.fromisoformat(value) for value in (transaction, settlement)]
            if [d.isoformat() for d in dates] != [transaction, settlement] or dates[1] < dates[0]:
                raise ValueError("Invalid statement dates")
            lines.append(
                StatementLine(
                    provider,
                    external,
                    Decimal(amount),
                    currency,
                    dates[0],
                    dates[1],
                    direction,
                    status,
                )
            )
        if not lines:
            raise ValueError("Empty statement")
    except (ValueError, csv.Error) as exc:
        raise AppError(422, "invalid_statement", "Invalid simulated statement CSV.") from exc
    return lines
