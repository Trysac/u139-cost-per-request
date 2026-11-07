"""CLI entry point for trysac-cost-per-request."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from decimal import Decimal, DecimalException

from cost_per_request.allocator import (
    AllocationError,
    CostBucket,
    UsageRecord,
    allocate,
)


def _load_costs(costs_path: str) -> list[CostBucket]:
    buckets: list[CostBucket] = []
    try:
        with open(costs_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            required = {"service", "amount", "currency"}
            if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
                raise ValueError(f"missing required header columns: {required}")
            for line_idx, row in enumerate(reader, start=2):
                service = (row.get("service") or "").strip()
                amount_str = (row.get("amount") or "").strip()
                currency = (row.get("currency") or "").strip()
                try:
                    amount = Decimal(amount_str)
                except (DecimalException, TypeError) as exc:
                    raise ValueError(f"line {line_idx}: invalid amount '{amount_str}'") from exc
                try:
                    buckets.append(CostBucket(service=service, amount=amount, currency=currency))
                except AllocationError as exc:
                    raise ValueError(f"line {line_idx}: {exc.message}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read costs file: {exc}") from exc
    return buckets


def _load_usage(usage_path: str) -> list[UsageRecord]:
    records: list[UsageRecord] = []
    try:
        with open(usage_path, encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    data = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"line {line_idx}: invalid JSON") from exc
                if not isinstance(data, dict):
                    raise ValueError(f"line {line_idx}: expected JSON object")
                customer = data.get("customer")
                service = data.get("service")
                duration_ms = data.get("duration_ms", 0)
                bytes_val = data.get("bytes", 0)
                try:
                    records.append(
                        UsageRecord(
                            customer=customer if customer is not None else "",
                            service=service if service is not None else "",
                            duration_ms=duration_ms,
                            bytes=bytes_val,
                        )
                    )
                except AllocationError as exc:
                    raise ValueError(f"line {line_idx}: {exc.message}") from exc
    except OSError as exc:
        raise ValueError(f"cannot read usage file: {exc}") from exc
    return records


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cost-per-request",
        description="Allocate infrastructure cost buckets to customers.",
    )
    parser.add_argument("--costs", required=True, help="Path to costs CSV file")
    parser.add_argument("--usage", required=True, help="Path to usage JSONL file")
    parser.add_argument(
        "--weight",
        default="requests",
        choices=["requests", "duration_ms", "bytes"],
        help="Metric to weight allocation by (default: requests)",
    )
    parser.add_argument(
        "--quantum",
        default="0.01",
        help="Smallest currency unit for largest-remainder rounding (default: 0.01)",
    )

    # Manual check for unknown arguments / unknown --weight to cleanly exit with 2
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code if isinstance(exc.code, int) else 2

    try:
        quantum_dec = Decimal(args.quantum)
    except DecimalException:
        sys.stderr.write(f"invalid quantum: {args.quantum}\n")
        return 2

    try:
        buckets = _load_costs(args.costs)
        records = _load_usage(args.usage)
        allocation = allocate(
            costs=buckets,
            usage=records,
            weight=args.weight,
            quantum=quantum_dec,
        )
    except (ValueError, AllocationError) as exc:
        sys.stderr.write(f"{exc}\n")
        return 2

    writer = csv.writer(sys.stdout)
    writer.writerow(["customer", "service", "requests", "cost"])
    # rows sorted by customer then service
    sorted_lines = sorted(allocation.lines, key=lambda item: (item.customer, item.service))
    for line in sorted_lines:
        writer.writerow([line.customer, line.service, line.requests, str(line.cost)])

    return 0


if __name__ == "__main__":
    sys.exit(main())
