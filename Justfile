import 'justfiles/github.just'
import 'justfiles/tessl.just'

default:
    @just --list

# Install dependencies and the workspace in development mode
sync:
    uv sync

# Run the tests, e.g. `just test -m "not docker"` to leave out Docker ones
[positional-arguments]
test *args:
    uv run pytest "$@"

# Run tests under coverage and report it, e.g. `just cover -m "not docker"`
[positional-arguments]
cover *args:
    uv run coverage run -m pytest "$@"
    uv run coverage report

# Format check, lint and validate the Polylith workspace
check:
    uv run ruff format --check .
    uv run ruff check .
    uv run poly check

# Run the poly CLI, e.g. `just poly create component --name <brick>`
[positional-arguments]
poly *args:
    @uv run poly "$@"

# Build the mono-bricks wheel into projects/bricks/dist
build:
    uv build --wheel projects/bricks

# Workspace summary and brick dependencies
info:
    uv run poly info
    uv run poly deps

# Python REPL with the dev helpers imported
repl:
    uv run python -i development/dev.py
