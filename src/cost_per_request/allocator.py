"""Cost allocation engine implementing the largest-remainder method with Decimal precision."""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import ROUND_FLOOR, ROUND_HALF_EVEN, Context, Decimal, DecimalException
from typing import Any, Literal

logger = logging.getLogger(__name__)

AllocationErrorCode = Literal[
    "invalid_amount",
    "currency_mismatch",
    "invalid_record",
    "too_many_customers",
    "unknown_customer",
]

WeightMetric = Literal["requests", "duration_ms", "bytes"]

MAX_INPUT_DISPLAY_LEN = 200
MAX_NAME_LEN = 200


def _truncate_msg(val: Any) -> str:
    text = str(val)
    if len(text) > MAX_INPUT_DISPLAY_LEN:
        return text[:MAX_INPUT_DISPLAY_LEN] + "..."
    return text


class AllocationError(Exception):
    """Base exception raised by cost allocation operations."""

    def __init__(self, code: AllocationErrorCode, message: str) -> None:
        super().__init__(message)
        self.code: AllocationErrorCode = code
        self.message = message


@dataclass(frozen=True)
class CostBucket:
    """Cost bucket for a specific service."""

    service: str
    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        # Validate service
        if not isinstance(self.service, str) or not (1 <= len(self.service) <= MAX_NAME_LEN):
            msg = _truncate_msg(self.service)
            raise AllocationError(
                "invalid_record",
                f"service must be a string of 1 to {MAX_NAME_LEN} characters, got: {msg}",
            )
        # Validate currency
        if not isinstance(self.currency, str) or not (1 <= len(self.currency) <= MAX_NAME_LEN):
            msg = _truncate_msg(self.currency)
            raise AllocationError(
                "currency_mismatch",
                f"currency must be a string of 1 to {MAX_NAME_LEN} characters, got: {msg}",
            )
        # Validate amount type (no floats)
        if isinstance(self.amount, float):
            raise AllocationError(
                "invalid_amount",
                f"float amount is not supported, use Decimal or str: {_truncate_msg(self.amount)}",
            )
        # Coerce/validate Decimal
        if isinstance(self.amount, str):
            try:
                dec_amt = Decimal(self.amount)
            except DecimalException as exc:
                raise AllocationError(
                    "invalid_amount",
                    f"amount string is invalid: {_truncate_msg(self.amount)}",
                ) from exc
            object.__setattr__(self, "amount", dec_amt)
        elif isinstance(self.amount, Decimal):
            dec_amt = self.amount
        else:
            amt_type = type(self.amount).__name__
            amt_str = _truncate_msg(self.amount)
            raise AllocationError(
                "invalid_amount",
                f"amount must be Decimal or str, got {amt_type}: {amt_str}",
            )

        if not dec_amt.is_finite() or dec_amt < Decimal(0):
            raise AllocationError(
                "invalid_amount",
                f"amount must be finite and non-negative: {_truncate_msg(dec_amt)}",
            )


@dataclass(frozen=True)
class UsageRecord:
    """One request of usage by a customer on a service."""

    customer: str
    service: str
    duration_ms: int = 0
    bytes: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.customer, str) or not (1 <= len(self.customer) <= MAX_NAME_LEN):
            msg = _truncate_msg(self.customer)
            raise AllocationError(
                "invalid_record",
                f"customer must be a string of 1 to {MAX_NAME_LEN} characters, got: {msg}",
            )
        if not isinstance(self.service, str) or not (1 <= len(self.service) <= MAX_NAME_LEN):
            msg = _truncate_msg(self.service)
            raise AllocationError(
                "invalid_record",
                f"service must be a string of 1 to {MAX_NAME_LEN} characters, got: {msg}",
            )
        if (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or self.duration_ms < 0
        ):
            msg = _truncate_msg(self.duration_ms)
            raise AllocationError(
                "invalid_record",
                f"duration_ms must be a non-negative integer, got: {msg}",
            )
        if isinstance(self.bytes, bool) or not isinstance(self.bytes, int) or self.bytes < 0:
            raise AllocationError(
                "invalid_record",
                f"bytes must be a non-negative integer, got: {_truncate_msg(self.bytes)}",
            )


@dataclass(frozen=True)
class AllocationLine:
    """Detailed allocation row for a (customer, service) pair."""

    customer: str
    service: str
    requests: int
    weight: int
    cost: Decimal


@dataclass(frozen=True)
class Allocation:
    """Result of allocating costs across usage records."""

    lines: tuple[AllocationLine, ...]
    by_customer: dict[str, Decimal]
    unallocated: dict[str, Decimal]
    unmatched_records: int
    currency: str
    customer_requests: dict[str, int]


@dataclass
class _UsageAggregate:
    requests: int = 0
    duration_ms: int = 0
    bytes: int = 0


def allocate(
    costs: Sequence[CostBucket],
    usage: Iterable[UsageRecord],
    *,
    weight: WeightMetric = "requests",
    quantum: Decimal = Decimal("0.01"),
    max_customers: int = 100_000,
) -> Allocation:
    """Allocate cost buckets to customers based on the selected weight metric."""
    if weight not in ("requests", "duration_ms", "bytes"):
        raise AllocationError(
            "invalid_record",
            f"unrecognized weight metric: {_truncate_msg(weight)}",
        )
    if not isinstance(quantum, Decimal) or not quantum.is_finite() or quantum <= Decimal(0):
        raise AllocationError(
            "invalid_amount",
            f"quantum must be a positive finite Decimal: {_truncate_msg(quantum)}",
        )

    # Validate and group cost buckets
    service_costs: dict[str, Decimal] = {}
    currency: str = ""

    for bucket in costs:
        if not isinstance(bucket, CostBucket):
            raise AllocationError(
                "invalid_record",
                f"costs sequence must contain CostBucket instances, got {type(bucket).__name__}",
            )
        if not currency:
            currency = bucket.currency
        elif bucket.currency != currency:
            raise AllocationError(
                "currency_mismatch",
                f"Currency mismatch: expected {currency}, got {bucket.currency}",
            )

        # Bucket amount must be an exact multiple of quantum
        rem = bucket.amount % quantum
        if rem != Decimal(0):
            raise AllocationError(
                "invalid_amount",
                f"Amount {bucket.amount} is not a multiple of quantum {quantum}",
            )

        service_costs[bucket.service] = (
            service_costs.get(bucket.service, Decimal(0)) + bucket.amount
        )

    # Stream usage records with bounded aggregation: keyed by (service, customer)
    known_services = set(service_costs.keys())
    unmatched_records = 0
    aggregates: dict[tuple[str, str], _UsageAggregate] = {}
    seen_customers: set[str] = set()
    customer_requests: dict[str, int] = {}

    for record in usage:
        if not isinstance(record, UsageRecord):
            raise AllocationError(
                "invalid_record",
                f"usage iterable must yield UsageRecord instances, got {type(record).__name__}",
            )

        if record.customer not in seen_customers:
            if len(seen_customers) >= max_customers:
                raise AllocationError(
                    "too_many_customers",
                    f"Number of distinct customers exceeded max_customers limit of {max_customers}",
                )
            seen_customers.add(record.customer)

        customer_requests[record.customer] = customer_requests.get(record.customer, 0) + 1

        if record.service not in known_services:
            unmatched_records += 1
            continue

        key = (record.service, record.customer)
        agg = aggregates.get(key)
        if agg is None:
            agg = _UsageAggregate()
            aggregates[key] = agg
        agg.requests += 1
        agg.duration_ms += record.duration_ms
        agg.bytes += record.bytes

    # Group aggregated usage by service
    service_to_cust_agg: dict[str, dict[str, _UsageAggregate]] = {}
    for (svc, cust), agg in aggregates.items():
        if svc not in service_to_cust_agg:
            service_to_cust_agg[svc] = {}
        service_to_cust_agg[svc][cust] = agg

    # Allocate each bucket
    calc_ctx = Context(prec=28)
    allocation_lines: list[AllocationLine] = []
    by_customer: dict[str, Decimal] = {}
    unallocated: dict[str, Decimal] = {}

    for svc in sorted(service_costs.keys()):
        amount = service_costs[svc]
        cust_map = service_to_cust_agg.get(svc, {})

        # Extract weights
        weights: dict[str, int] = {}
        for cust, agg in cust_map.items():
            if weight == "requests":
                w = agg.requests
            elif weight == "duration_ms":
                w = agg.duration_ms
            elif weight == "bytes":
                w = agg.bytes
            else:
                w = 0
            weights[cust] = w

        total_weight = sum(weights.values())
        if total_weight == 0:
            unallocated[svc] = amount
            # Lines for services where requests > 0 but weight is 0 (e.g. bytes=0)
            for cust in sorted(cust_map.keys()):
                agg = cust_map[cust]
                allocation_lines.append(
                    AllocationLine(
                        customer=cust,
                        service=svc,
                        requests=agg.requests,
                        weight=weights.get(cust, 0),
                        cost=Decimal(0),
                    )
                )
            continue

        # Largest remainder method
        # Exact share s = amount * w / W using Decimal context with 28 digits
        floors: dict[str, Decimal] = {}
        remainders: list[tuple[Decimal, str]] = []
        sum_floors = Decimal(0)

        w_decimal = Decimal(total_weight)
        for cust in sorted(cust_map.keys()):
            w_val = Decimal(weights[cust])
            share = calc_ctx.divide(calc_ctx.multiply(amount, w_val), w_decimal)
            quanta_count = (share / quantum).to_integral_value(rounding=ROUND_FLOOR)
            floor_amt = quanta_count * quantum
            floors[cust] = floor_amt
            rem = share - floor_amt
            sum_floors += floor_amt
            remainders.append((rem, cust))

        # Remaining quanta to distribute
        leftover_amount = amount - sum_floors
        leftover_quanta = int((leftover_amount / quantum).to_integral_value())

        # Sort remainders: largest remainder first, ties by customer ascending
        # In Python sort: (-rem, cust)
        remainders.sort(key=lambda item: (-item[0], item[1]))

        allocations: dict[str, Decimal] = dict(floors)
        for i in range(leftover_quanta):
            cust = remainders[i][1]
            allocations[cust] += quantum

        for cust in sorted(cust_map.keys()):
            cust_cost = allocations[cust]
            agg = cust_map[cust]
            allocation_lines.append(
                AllocationLine(
                    customer=cust,
                    service=svc,
                    requests=agg.requests,
                    weight=weights[cust],
                    cost=cust_cost,
                )
            )
            by_customer[cust] = by_customer.get(cust, Decimal(0)) + cust_cost

    # Sort lines by customer, then service
    allocation_lines.sort(key=lambda line: (line.customer, line.service))

    return Allocation(
        lines=tuple(allocation_lines),
        by_customer=by_customer,
        unallocated=unallocated,
        unmatched_records=unmatched_records,
        currency=currency,
        customer_requests=customer_requests,
    )


def cost_per_request(allocation: Allocation, customer: str) -> Decimal:
    """Compute the average cost per request for a customer rounded to 6 decimal places."""
    if customer not in allocation.customer_requests:
        raise AllocationError(
            "unknown_customer",
            f"Unknown customer: {_truncate_msg(customer)}",
        )
    total_requests = allocation.customer_requests[customer]
    if total_requests == 0:
        # By construction seen customers have at least 1 request, but guard against zero
        return Decimal("0.000000")
    customer_cost = allocation.by_customer.get(customer, Decimal(0))
    calc_ctx = Context(prec=28)
    avg = calc_ctx.divide(customer_cost, Decimal(total_requests))
    return avg.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
