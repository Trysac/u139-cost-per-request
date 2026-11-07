# Architecture

`cost-per-request` is a streaming allocation engine using exact Decimal arithmetic.

## Components

1. **Data Models**:
   - `CostBucket`, `UsageRecord`, `AllocationLine`, `Allocation`.

2. **Allocation Engine**:
   - Sums multiple buckets for the same service.
   - Computes exact quota $s = \text{amount} \times w / W$ using a high-precision 28-digit Decimal context.
   - Assigns the integer floor of quanta to each customer.
   - Distributes remainder quanta based on largest fractional parts, breaking ties by customer ID ascending.
   - Ensures that the sum of parts equals the bucket amount exactly.

3. **Aggregation**:
   - Streams usage and aggregates only by `(service, customer)` to maintain bounded memory usage (independent of record count).
   - Enforces a `max_customers` limit to prevent memory exhaustion.