# Tessl plugins

mono-python's [Tessl](https://tessl.io) plugins: the rules an agent
loads, each distilled from the recipes under `docs/recipes/` that carry
its `<!-- tessl-plugin: <name> -->` label. A workspace built on these
bricks installs them alongside its own, so the rules travel with the
docs they cite.

- **docs** — how to write or check anything under `docs/`: the recipe
  and TDD shapes, wrap-80, link hygiene, mermaid and tone, and the
  `check-docs` skill that verifies them.

`plugins/profiles` names which plugins a profile links. `just
tessl-plugins-install` installs every plugin from the working tree and
lays the active profile down in `.tessl/RULES.md`; `just
tessl-plugins-check` reports an installed copy behind its source.

A workspace that installs these plugins beside its own sets
`TESSL_PLUGIN_ROOTS` to both roots — its `plugins` and the directory it
laid mono-python's down in — and names both workspaces' plugins in its
`plugins/profiles`. The recipes install and check every root in that
order.
