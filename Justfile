import 'justfiles/github.just'
import 'justfiles/tessl.just'

# Every recipe below needs the flake's toolchain, uv above all: the system
# may carry uv too, at a different version, so a bare `uv run pytest` looks
# like it works and then fails the Docker-backed tests with a 500 from the
# daemon rather than anything that names the real cause.
#
# direnv loads the dev shell on entry, so an interactive session is already
# inside one and re-entering would cost seconds per recipe. An agent or a CI
# step invoking `just test` straight is not, and gets whatever is on PATH.
# `nix develop` and direnv's `use flake` both set IN_NIX_SHELL, which is what
# tells the two apart.
flake := if env_var_or_default("IN_NIX_SHELL", "") == "" { "nix develop . --command" } else { "" }

default:
    @just --list

# Install dependencies and the workspace in development mode
sync:
    {{ flake }} uv sync

# Run the tests, e.g. `just test -m "not docker"` to leave out Docker ones
[positional-arguments]
test *args:
    {{ flake }} uv run pytest "$@"

# Run tests under coverage and report it, e.g. `just cover -m "not docker"`
[positional-arguments]
cover *args:
    {{ flake }} uv run coverage run -m pytest "$@"
    {{ flake }} uv run coverage report

# Format check, lint and validate the Polylith workspace
check:
    {{ flake }} uv run ruff format --check .
    {{ flake }} uv run ruff check .
    {{ flake }} uv run poly check

# Run the poly CLI, e.g. `just poly create component --name <brick>`
[positional-arguments]
poly *args:
    @{{ flake }} uv run poly "$@"

# Build the mono-bricks wheel into projects/bricks/dist
build:
    {{ flake }} uv build --wheel projects/bricks

# Workspace summary and brick dependencies
info:
    {{ flake }} uv run poly info
    {{ flake }} uv run poly deps

# Python REPL with the dev helpers imported
repl:
    {{ flake }} uv run python -i development/dev.py
