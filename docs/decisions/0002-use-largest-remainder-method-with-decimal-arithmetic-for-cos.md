# Use Largest Remainder Method with Decimal Arithmetic for Cost Allocation

Status: accepted (generated, pending human review)

## Context

Traditional spreadsheet-based infrastructure cost allocation calculates customer shares as rounded floating-point percentages, causing the sum of allocations to diverge from the total cloud invoice amount. In enterprise billing and chargeback, line items must reconcile to the exact penny without rounding discrepancies.

## Decision

Implement the largest remainder method (Hare-Niemeyer quota allocation) using Python's stdlib `decimal` module with 28 digits of precision. Each bucket amount is partitioned into integer multiples of a specified `quantum` (default 0.01). Quotas are floored, and leftover quanta are awarded to customers with the largest fractional remainders, resolving ties by alphabetical order of customer identifier.

## Consequences

Allocated parts are guaranteed by construction to sum exactly to the original bucket amount without floating-point artifacts. Aggregation is streaming and bounded by `(service, customer)` pairs, maintaining $O(\text{customers} \times \text{services})$ memory footprint even when ingesting millions of request records.
