# Security notes

## Threat model

`cost-per-request` is a library without I/O; threats are mitigated by design.

- **Input Validation**: All inputs (`CostBucket`, `UsageRecord`, `allocate`) are validated. Strings are capped at 200 characters, float values are rejected, and non-finite Decimal values trigger errors.
- **Resource Exhaustion**: The library limits the number of distinct customers via `max_customers` to prevent DoS attacks on memory usage. Aggregation is streaming-only.
- **Execution Risks**: No `eval`, `exec`, or unsafe deserialization. Messages in `AllocationError` are truncated to 200 characters to prevent log injection or memory issues.