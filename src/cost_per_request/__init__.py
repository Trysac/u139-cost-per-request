"""Infrastructure cost allocation by request, duration, or bytes with exact Decimal arithmetic."""

from __future__ import annotations

import logging

from cost_per_request.allocator import (
    Allocation,
    AllocationError,
    AllocationErrorCode,
    AllocationLine,
    CostBucket,
    UsageRecord,
    WeightMetric,
    allocate,
    cost_per_request,
)

__all__ = [
    "Allocation",
    "AllocationError",
    "AllocationErrorCode",
    "AllocationLine",
    "CostBucket",
    "UsageRecord",
    "WeightMetric",
    "__version__",
    "allocate",
    "cost_per_request",
]

__version__ = "0.1.0"

logging.getLogger(__name__).addHandler(logging.NullHandler())
