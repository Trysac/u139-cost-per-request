# Project record

## Objective

Allocate infrastructure cost buckets to customers by requests, duration or bytes with Decimal largest-remainder rounding, then report cost per request.

## Scope

- **In scope**: Library implementation of cost allocation using `Decimal` arithmetic, CLI for processing CSV costs and JSONL usage, and validation logic.
- **Out of scope**: Fetching bills from cloud provider APIs, time-windowed allocation, cost amortization, and automated currency conversion.

## Factory run u139 (measured from API usage)

| Phase | Model | Batch | Input | Output | Cache write | Cache read | Cost (USD) |
|---|---|---|---|---|---|---|---|
| generation | gemini-3.8-flash | yes | 4122 | 11654 | 0 | 0 | 0.0234 |
| fix-1 | gemini-3.8-flash | no | 20521 | 1998 | 0 | 31212 | 0.0252 |
| fix-2 | gemini-3.8-flash | no | 13485 | 138 | 0 | 9236 | 0.0113 |
| audit | gemini-3.1-flash-lite | no | 47683 | 381 | 0 | 77369 | 0.0144 |
| fix-3 | gemini-3.8-flash | no | 95131 | 626 | 0 | 939254 | 0.1441 |
| docs | gemini-3.1-flash-lite | no | 160917 | 1657 | 0 | 0 | 0.0427 |

Total: $0.2612. Prices: Anthropic list prices.
