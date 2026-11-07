# Testing

## Test Coverage

- `tests/test_cost_per_request.py`: Contains unit and acceptance tests verifying the allocation logic, validation errors, and largest-remainder rounding math.

## Execution

- Tests cover the public API (`import cost_per_request`) and assert every observable effect, including return values and raised `AllocationError` instances with correct codes.