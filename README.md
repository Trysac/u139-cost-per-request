# cost-per-request

Platform teams know the monthly bill per service but not what each customer costs, so pricing and abuse discussions rely on guesses. Spreadsheet allocations round each share independently and the totals no longer match the invoice. This library streams usage records, allocates each cost bucket by a chosen weight with exact Decimal arithmetic so the parts always sum to the bucket, and reports cost per customer and per request.

## Installation

```bash
pip install cost-per-request
```

## Usage Example

```python
from decimal import Decimal
from cost_per_request import CostBucket, UsageRecord, allocate, cost_per_request

costs = [CostBucket("api", Decimal("10.00"), "USD")]
usage = [UsageRecord("a", "api"), UsageRecord("b", "api"), UsageRecord("c", "api")]
allocation = allocate(costs, usage, weight="requests")
print(allocation.by_customer)  # {'a': Decimal('3.34'), 'b': Decimal('3.33'), 'c': Decimal('3.33')}
print(cost_per_request(allocation, "a"))  # Decimal('1.113333')
```

## Public API Summary

- `CostBucket(service: str, amount: Decimal, currency: str)`: Represents a cost line item.
- `UsageRecord(customer: str, service: str, duration_ms: int = 0, bytes: int = 0)`: Represents one request event.
- `allocate(...) -> Allocation`: Allocates costs using the largest-remainder method.
- `cost_per_request(allocation, customer: str) -> Decimal`: Calculates average cost per request.

### Limits and Options

- **Weights**: `requests`, `duration_ms`, `bytes`.
- **Error Codes**: `invalid_amount`, `currency_mismatch`, `invalid_record`, `too_many_customers`, `unknown_customer`.
- **Constraints**: Float amounts are rejected; bucket amounts must be multiples of `quantum`.

## Why not spreadsheet shares?

Spreadsheets often round shares independently, leading to totals that do not match the original invoice. This utility guarantees exact sums by construction using the largest-remainder method, provides a deterministic tie-breaking rule, and handles streaming input to keep memory usage bounded.

For details on security, see [docs/SECURITY.md](docs/SECURITY.md).