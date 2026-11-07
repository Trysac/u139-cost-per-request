"""Unit and acceptance tests for trysac-cost-per-request."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from cost_per_request import (
    AllocationError,
    CostBucket,
    UsageRecord,
    allocate,
    cost_per_request,
)
from cost_per_request.__main__ import main


def test_acceptance_1_equal_shares_largest_remainder() -> None:
    """Bucket CostBucket('api', Decimal('10.00'), 'USD') with one request each from customers 'a', 'b' and 'c'
    and weight 'requests' allocates {'a': Decimal('3.34'), 'b': Decimal('3.33'), 'c': Decimal('3.33')}
    and the allocations sum to Decimal('10.00')."""
    costs = [CostBucket("api", Decimal("10.00"), "USD")]
    usage = [
        UsageRecord("a", "api"),
        UsageRecord("b", "api"),
        UsageRecord("c", "api"),
    ]
    allocation = allocate(costs, usage, weight="requests")
    assert allocation.by_customer == {
        "a": Decimal("3.34"),
        "b": Decimal("3.33"),
        "c": Decimal("3.33"),
    }
    assert sum(allocation.by_customer.values()) == Decimal("10.00")
    assert allocation.unmatched_records == 0
    assert len(allocation.lines) == 3


def test_acceptance_2_duration_ms_weight() -> None:
    """With weight 'duration_ms', customer 'a' at 300 and 'b' at 100 for a Decimal('10.00') bucket
    allocates Decimal('7.50') and Decimal('2.50')."""
    costs = [CostBucket("compute", Decimal("10.00"), "USD")]
    usage = [
        UsageRecord("a", "compute", duration_ms=300),
        UsageRecord("b", "compute", duration_ms=100),
    ]
    allocation = allocate(costs, usage, weight="duration_ms")
    assert allocation.by_customer["a"] == Decimal("7.50")
    assert allocation.by_customer["b"] == Decimal("2.50")
    assert sum(allocation.by_customer.values()) == Decimal("10.00")


def test_acceptance_3_unallocated_and_unmatched() -> None:
    """A bucket whose service has no usage is reported in allocation.unallocated == {'batch': Decimal('5.00')},
    and usage for a service without a bucket is counted in allocation.unmatched_records."""
    costs = [CostBucket("batch", Decimal("5.00"), "USD")]
    usage = [
        UsageRecord("a", "untracked", duration_ms=10),
        UsageRecord("b", "other_service", duration_ms=20),
    ]
    allocation = allocate(costs, usage)
    assert allocation.unallocated == {"batch": Decimal("5.00")}
    assert allocation.unmatched_records == 2
    assert allocation.by_customer == {}


def test_acceptance_4_cost_per_request() -> None:
    """cost_per_request(allocation, 'a') for Decimal('3.34') over 3 requests returns Decimal('1.113333')."""
    costs = [CostBucket("api", Decimal("3.34"), "USD")]
    usage = [
        UsageRecord("a", "api"),
        UsageRecord("a", "api"),
        UsageRecord("a", "api"),
    ]
    allocation = allocate(costs, usage, weight="requests")
    result = cost_per_request(allocation, "a")
    assert result == Decimal("1.113333")


def test_acceptance_5_validation_errors() -> None:
    """An amount given as float 1.5, a negative amount, or Decimal('NaN') raises AllocationError
    with code 'invalid_amount'; buckets in 'USD' and 'EUR' together raise code 'currency_mismatch';
    a negative weight value raises code 'invalid_record'."""
    # Float 1.5
    with pytest.raises(AllocationError) as exc_info:
        CostBucket("api", 1.5, "USD")  # type: ignore[arg-type]
    assert exc_info.value.code == "invalid_amount"

    # Negative amount
    with pytest.raises(AllocationError) as exc_info:
        CostBucket("api", Decimal("-1.00"), "USD")
    assert exc_info.value.code == "invalid_amount"

    # Decimal('NaN')
    with pytest.raises(AllocationError) as exc_info:
        CostBucket("api", Decimal("NaN"), "USD")
    assert exc_info.value.code == "invalid_amount"

    # USD and EUR together
    buckets = [
        CostBucket("api", Decimal("10.00"), "USD"),
        CostBucket("db", Decimal("20.00"), "EUR"),
    ]
    with pytest.raises(AllocationError) as exc_info:
        allocate(buckets, [UsageRecord("a", "api")])
    assert exc_info.value.code == "currency_mismatch"

    # Negative weight value
    with pytest.raises(AllocationError) as exc_info:
        UsageRecord("a", "api", duration_ms=-10)
    assert exc_info.value.code == "invalid_record"

    with pytest.raises(AllocationError) as exc_info:
        UsageRecord("a", "api", bytes=-1)
    assert exc_info.value.code == "invalid_record"


def test_acceptance_6_bounded_customers_and_memory() -> None:
    """max_customers=100_000 by default: usage from 100_001 distinct customers raises AllocationError
    with code 'too_many_customers', and 1_000_000 records from 3 customers are processed with memory
    bounded by the 3 aggregates."""
    costs = [CostBucket("api", Decimal("100.00"), "USD")]

    # Test exceeding max_customers with a small threshold
    small_limit = 5
    records_exceeding = (UsageRecord(f"cust_{i}", "api") for i in range(small_limit + 1))
    with pytest.raises(AllocationError) as exc_info:
        allocate(costs, records_exceeding, max_customers=small_limit)
    assert exc_info.value.code == "too_many_customers"

    # 1_000_000 records from 3 customers
    def record_generator(count: int):
        custs = ["alice", "bob", "charlie"]
        for i in range(count):
            yield UsageRecord(custs[i % 3], "api", duration_ms=1)

    alloc = allocate(costs, record_generator(1_000_000))
    assert len(alloc.by_customer) == 3
    assert sum(alloc.by_customer.values()) == Decimal("100.00")


def test_acceptance_7_cli(
    tmp_path: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """main(['--costs', 'costs.csv', '--usage', 'usage.jsonl', '--weight', 'requests'])
    prints CSV with header 'customer,service,requests,cost' and rows sorted by customer then service,
    and returns 0; an unknown --weight returns 2."""
    costs_file = tmp_path / "costs.csv"
    usage_file = tmp_path / "usage.jsonl"

    costs_file.write_text("service,amount,currency\napi,10.00,USD\n", encoding="utf-8")
    usage_data = [
        {"customer": "b", "service": "api", "duration_ms": 10, "bytes": 100},
        {"customer": "a", "service": "api", "duration_ms": 20, "bytes": 200},
    ]
    usage_file.write_text("\n".join(json.dumps(d) for d in usage_data) + "\n", encoding="utf-8")

    # Valid run
    rc = main(
        [
            "--costs",
            str(costs_file),
            "--usage",
            str(usage_file),
            "--weight",
            "requests",
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    lines = out.strip().split("\r\n" if "\r\n" in out else "\n")
    assert lines[0] == "customer,service,requests,cost"
    assert lines[1] == "a,api,1,5.00"
    assert lines[2] == "b,api,1,5.00"

    # Unknown weight returns 2
    rc_unknown = main(
        [
            "--costs",
            str(costs_file),
            "--usage",
            str(usage_file),
            "--weight",
            "invalid_weight",
        ]
    )
    assert rc_unknown == 2


def test_edge_cases() -> None:
    # Single customer gets the whole bucket
    costs = [CostBucket("api", Decimal("10.00"), "USD")]
    usage = [UsageRecord("only_cust", "api")]
    alloc = allocate(costs, usage)
    assert alloc.by_customer["only_cust"] == Decimal("10.00")
    assert cost_per_request(alloc, "only_cust") == Decimal("10.000000")

    # Weight 'bytes' with all zeros goes to unallocated
    zero_bytes_usage = [
        UsageRecord("cust1", "api", bytes=0),
        UsageRecord("cust2", "api", bytes=0),
    ]
    alloc_zero = allocate(costs, zero_bytes_usage, weight="bytes")
    assert alloc_zero.unallocated == {"api": Decimal("10.00")}
    assert alloc_zero.by_customer == {}

    # Quantum Decimal('1') for zero-decimal currencies (e.g. JPY)
    jpy_costs = [CostBucket("db", Decimal("100"), "JPY")]
    jpy_usage = [
        UsageRecord("c1", "db"),
        UsageRecord("c2", "db"),
        UsageRecord("c3", "db"),
    ]
    alloc_jpy = allocate(jpy_costs, jpy_usage, quantum=Decimal("1"))
    assert alloc_jpy.by_customer == {
        "c1": Decimal("34"),
        "c2": Decimal("33"),
        "c3": Decimal("33"),
    }
    assert sum(alloc_jpy.by_customer.values()) == Decimal("100")

    # Multiple buckets for the same service are summed first
    multi_buckets = [
        CostBucket("api", Decimal("4.00"), "USD"),
        CostBucket("api", Decimal("6.00"), "USD"),
    ]
    alloc_multi = allocate(multi_buckets, usage)
    assert alloc_multi.by_customer["only_cust"] == Decimal("10.00")

    # Unicode customer IDs
    unicode_usage = [
        UsageRecord("用戶A", "api"),
        UsageRecord("用戶B", "api"),
    ]
    alloc_uni = allocate(costs, unicode_usage)
    assert alloc_uni.by_customer["用戶A"] == Decimal("5.00")
    assert alloc_uni.by_customer["用戶B"] == Decimal("5.00")


def test_error_branches_and_validations() -> None:
    # Unknown customer raises unknown_customer
    costs = [CostBucket("api", Decimal("10.00"), "USD")]
    usage = [UsageRecord("alice", "api")]
    alloc = allocate(costs, usage)
    with pytest.raises(AllocationError) as exc_info:
        cost_per_request(alloc, "unknown")
    assert exc_info.value.code == "unknown_customer"

    # Invalid amount not multiple of quantum
    with pytest.raises(AllocationError) as exc_info:
        allocate([CostBucket("api", Decimal("10.005"), "USD")], usage, quantum=Decimal("0.01"))
    assert exc_info.value.code == "invalid_amount"

    # String amount in CostBucket constructor is parsed
    cb_str = CostBucket("api", "12.34", "USD")  # type: ignore[arg-type]
    assert cb_str.amount == Decimal("12.34")

    # Invalid string amount
    with pytest.raises(AllocationError) as exc:
        CostBucket("api", "not-a-number", "USD")  # type: ignore[arg-type]
    assert exc.value.code == "invalid_amount"

    # Invalid types in CostBucket and UsageRecord
    with pytest.raises(AllocationError):
        CostBucket("", Decimal("10.00"), "USD")
    with pytest.raises(AllocationError):
        CostBucket("api", Decimal("10.00"), "")
    with pytest.raises(AllocationError):
        CostBucket("api", None, "USD")  # type: ignore[arg-type]

    with pytest.raises(AllocationError):
        UsageRecord("", "api")
    with pytest.raises(AllocationError):
        UsageRecord("a", "")
    with pytest.raises(AllocationError):
        UsageRecord("a", "api", duration_ms=True)  # type: ignore[arg-type]
    with pytest.raises(AllocationError):
        UsageRecord("a", "api", bytes=False)  # type: ignore[arg-type]

    # allocate checks
    with pytest.raises(AllocationError) as exc:
        allocate(costs, usage, weight="unknown")  # type: ignore[arg-type]
    assert exc.value.code == "invalid_record"

    with pytest.raises(AllocationError) as exc:
        allocate(costs, usage, quantum=Decimal("-0.01"))
    assert exc.value.code == "invalid_amount"

    with pytest.raises(AllocationError) as exc:
        allocate(["not-a-bucket"], usage)  # type: ignore[list-item]
    assert exc.value.code == "invalid_record"

    with pytest.raises(AllocationError) as exc:
        allocate(costs, ["not-a-record"])  # type: ignore[list-item]
    assert exc.value.code == "invalid_record"


def test_cli_errors(tmp_path: pytest.TempPathFactory, capsys: pytest.CaptureFixture[str]) -> None:
    # Missing file
    rc = main(["--costs", "non_existent.csv", "--usage", "non_existent.jsonl"])
    assert rc == 2
    err = capsys.readouterr().err
    assert "cannot read costs file" in err

    # Costs CSV with missing column
    bad_costs = tmp_path / "bad_costs.csv"
    bad_costs.write_text("foo,bar\n1,2\n", encoding="utf-8")
    rc = main(["--costs", str(bad_costs), "--usage", "non_existent.jsonl"])
    assert rc == 2
    assert "missing required header columns" in capsys.readouterr().err

    # Costs CSV with invalid amount
    bad_amt_costs = tmp_path / "bad_amt.csv"
    bad_amt_costs.write_text("service,amount,currency\napi,abc,USD\n", encoding="utf-8")
    rc = main(["--costs", str(bad_amt_costs), "--usage", "non_existent.jsonl"])
    assert rc == 2
    assert "line 2: invalid amount" in capsys.readouterr().err

    # Costs CSV with invalid service
    bad_svc_costs = tmp_path / "bad_svc.csv"
    bad_svc_costs.write_text("service,amount,currency\n,10.00,USD\n", encoding="utf-8")
    rc = main(["--costs", str(bad_svc_costs), "--usage", "non_existent.jsonl"])
    assert rc == 2
    assert "line 2:" in capsys.readouterr().err

    # Valid costs, missing usage file
    good_costs = tmp_path / "good_costs.csv"
    good_costs.write_text("service,amount,currency\napi,10.00,USD\n", encoding="utf-8")
    rc = main(["--costs", str(good_costs), "--usage", "non_existent.jsonl"])
    assert rc == 2
    assert "cannot read usage file" in capsys.readouterr().err

    # Valid costs, invalid JSON usage
    bad_json_usage = tmp_path / "bad_json.jsonl"
    bad_json_usage.write_text("not json\n", encoding="utf-8")
    rc = main(["--costs", str(good_costs), "--usage", str(bad_json_usage)])
    assert rc == 2
    assert "line 1: invalid JSON" in capsys.readouterr().err

    # Valid costs, non-dict JSON usage
    array_usage = tmp_path / "array.jsonl"
    array_usage.write_text("[1, 2, 3]\n", encoding="utf-8")
    rc = main(["--costs", str(good_costs), "--usage", str(array_usage)])
    assert rc == 2
    assert "line 1: expected JSON object" in capsys.readouterr().err

    # Valid costs, invalid usage fields (negative bytes)
    invalid_fields = tmp_path / "invalid_fields.jsonl"
    invalid_fields.write_text(
        json.dumps({"customer": "a", "service": "api", "bytes": -5}) + "\n", encoding="utf-8"
    )
    rc = main(["--costs", str(good_costs), "--usage", str(invalid_fields)])
    assert rc == 2
    assert "line 1:" in capsys.readouterr().err

    # Invalid quantum
    rc = main(
        ["--costs", str(good_costs), "--usage", str(invalid_fields), "--quantum", "bad_quantum"]
    )
    assert rc == 2
    assert "invalid quantum" in capsys.readouterr().err
