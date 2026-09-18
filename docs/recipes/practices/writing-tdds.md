# Writing TDDs

<!-- tessl-plugin: docs -->

## Problem

You're writing a technical design under `docs/tdd/` — the engineering
contract behind a brick: the concept it carries and the library chosen
to realise it, decided before the brick is written — and you want it
in the shape every other TDD has.

## Solution

A TDD is engineering prose: it names bricks, operations, libraries,
records and routes. Nothing distils it, and an agent opens it in full,
so it carries no `tessl-plugin` label. Its sections, in order, follow.
Formatting, links and tone are [writing-docs](writing-docs.md)'s.

### Status banner

A blockquote under the title, before the first section, opening with
`**Status: proposal.**` or `**Status: implemented.**`. A proposal's
banner says what already exists and that Background names it, that
everything under Proposed Solution is the build list, and which section
says what comes first. An implemented TDD's banner is the one line.

### Objective

`## Objective` is one paragraph of what the capability is and what the
TDD decides, then two paragraphs opening with the words `In scope:`
and `Out of scope:`, each a list of what this design does and does not
decide, with a link to the document that decides each thing left out.

### Background

`## Background` is what exists — the bricks, records, patterns and
tooling the design reuses — as bullets each opening with a bold label
and naming where the thing lives. Where the brick ports one of mono's,
the first bullet names that brick and what of its shape carries over:
its component kinds, config keys and operations, which the port is
faithful to. Nothing that will be built appears here.

### Proposed Solution

`## Proposed Solution` — `## Solution` once implemented — opens with
`### The library`: the Python library or standard-library module that
realises the concept, the candidates it was chosen over and why, and
what of it the brick exposes. Then one `###` per design area: the
brick, the component, the routes, the security, the fake or container
the tests run against. Each names the files it touches and the
operations, exceptions, config keys and schemas it adds. The last two
sub-sections are a first-slice section — a numbered list of what is
built first, and what follows under whose design — and `### Tests`,
one bullet per brick or base saying what its tests cover.

### Alternatives Considered

`## Alternatives Considered` is a bulleted list, each
`**The alternative.** Rejected:` and the reason in a sentence. A
library considered for `### The library` and not chosen is one. An
alternative taken in part says which part.

### Known Limitations

`## Known Limitations` is a bulleted list, each opening with a bold
label, of what the design leaves undone or unproved.

### References

`## References` lists the mono brick this design ports first, then
sibling TDDs, recipes, the chosen library's documentation and external
specifications, each as `[id](path) — gloss`, the gloss saying what
the document gives this design.

## Rules

**MUST:**

- Structure a TDD as a Status banner, Objective, Background, Proposed
  Solution, Alternatives Considered, Known Limitations, References.
- Open the Status banner with **proposal** or **implemented**. A
  proposal's banner names what exists, says the Proposed Solution is
  the build list, and names the section that says what comes first.
- Open the Objective's scope paragraphs with `In scope:` and
  `Out of scope:`, and link the document that decides each thing left
  out.
- Name the mono brick a design ports in Background, and what of its
  shape carries over.
- Open the Proposed Solution with `### The library`, naming the
  library or standard-library module that realises the concept and
  the candidates it was chosen over.
- End the Proposed Solution with a first-slice section and `### Tests`.
- Give each rejected alternative its reason in the sentence that
  rejects it.
- Rename Proposed Solution to Solution once the design is implemented,
  and the banner with it.

**MUST NOT:**

- Label a TDD `tessl-plugin`.
- Put anything that will be built in Background, or anything that
  exists in Proposed Solution as if it did not.
- Name a consuming workspace in a library workspace's TDD. The design
  serves every workspace built on the bricks.

## Discussion

We split a TDD along the line of what exists and what will be built
because a reader arrives with one of two questions — what do I build,
or what is here — and the two sections answer one each. The Status
banner's three sentences are what let a proposal be read long after
it was written without guessing which parts landed.

The library section leads because it is the decision a port makes
that mono did not. The concept is settled — mono's brick is what it
is — and what the TDD adds is which library carries it in Python,
read from that library's own documentation rather than remembered,
and what the brick hides of it.

The first-slice section is what turns a design into an order of work.
Each slice ends in something proved: a records slice in a migration
that runs, an API slice in scenarios that pass. Comparing the code
against the TDD once a slice lands is what shows the design drifting,
and is why the Proposed Solution names files and operations rather
than describing them.

## References

- [writing-docs](writing-docs.md) — formatting, links and tone, for
  everything under `docs/`.
- [smtp](https://github.com/repldriven/mono/blob/main/docs/tdd/smtp.md) —
  mono's SMTP design, a proposal TDD in this shape.
