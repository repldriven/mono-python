# CLAUDE.md

mono-python is a Python component library for composing systems from
independently testable bricks, organised as a
[Polylith](https://davidvujic.github.io/python-polylith-docs/) workspace
and ported from [repldriven/mono](https://github.com/repldriven/mono).
A workspace built on it consumes `projects/bricks` as a git dependency
pinned to a tag. See [README.md](README.md) for the bricks and how to
depend on them.

## Topic router

CLAUDE.md is the routing layer. Every `docs/recipes/*/*.md` file below
is labelled `<!-- tessl-plugin: <name> -->`, and that plugin's rule
(always loaded via `AGENTS.md`) already distils its `## Rules` — you
don't need to open the doc to rediscover that. Open it for the *why*
behind the rule instead: the Discussion.

`docs/tdd/` is the exception: nothing distils a TDD, so open it in
full before non-trivial work on its brick.

### Operations

- **Writing docs** — wrap at 80, link hygiene, mermaid, tone; the
  `check-docs` skill that verifies them; then what a recipe and a TDD
  are each made of.
  See [writing-docs.md](docs/recipes/practices/writing-docs.md),
  [writing-recipes.md](docs/recipes/practices/writing-recipes.md) and
  [writing-tdds.md](docs/recipes/practices/writing-tdds.md).
- **Tessl plugins** — the rules an agent loads, the roots they install
  from, profiles. See [plugins/README.md](plugins/README.md).

## Common commands

```bash
# Install dependencies and the workspace in development mode.
just sync

# Run the tests; leave out the Docker ones with -m "not docker".
just test
just test -m "not docker"

# Format check, lint and validate the Polylith workspace.
just check

# Install the Tessl plugins from the working tree, and check them.
just tessl-plugins-install
just tessl-plugins-check
```

@AGENTS.md
