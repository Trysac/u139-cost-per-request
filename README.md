# cost-per-request

[![PyPI version](https://img.shields.io/pypi/v/trysac-cost-per-request)](https://pypi.org/project/trysac-cost-per-request/)
[![License: MIT](https://img.shields.io/pypi/l/trysac-cost-per-request)](LICENSE)
[![CI](https://github.com/Trysac/u139-cost-per-request/actions/workflows/ci.yml/badge.svg)](https://github.com/Trysac/u139-cost-per-request/actions/workflows/ci.yml)

Allocate infrastructure cost buckets to customers by requests, duration or bytes with Decimal largest-remainder rounding, then report cost per request

## Problem

Describe in two or three sentences the concrete problem this utility solves, who hits it, and what
they do today without it. Replace this paragraph when the first real feature lands.

## Install

```sh
pip install trysac-cost-per-request
# or
uv add trysac-cost-per-request
```

Requires Python 3.10 or newer. No runtime dependencies.

## Usage

```python
import cost_per_request

# normalize() trims surrounding whitespace and lower-cases the text.
print(cost_per_request.normalize("  Hello World "))  # -> "hello world"

# Blank input is rejected explicitly instead of returning an empty string.
try:
    cost_per_request.normalize("   ")
except ValueError as exc:
    print(f"rejected: {exc}")
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) and [decisions](docs/decisions/)
- [Testing](docs/TESTING.md) and [security](docs/SECURITY.md)
- [Project record](docs/PROJECT.md) and [stack](docs/STACK.md)
- [Changelog](CHANGELOG.md) and [contributing guide](CONTRIBUTING.md)

## License

[MIT](LICENSE) (c) 2026 Miguel Gomez
