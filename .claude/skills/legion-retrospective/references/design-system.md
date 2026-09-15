# Retrospective design system

The exact visual system used for the first Legion retrospective (14 to 15
September 2026). Reuse these values unchanged, the same way this project
reuses its own validated product palette rather than re-picking colours each
release. Re-validate only if a fifth categorical series is ever needed.

This is a Bluestaq internal, analytical document, not the product's own
console interface. It deliberately uses the Bluestaq house palette (the
product UI deliberately does not; that is a separate, already-authorised
decision and this skill does not touch it).

## Why single-theme, light only

The first edition committed to one light, paper-like "dossier" look rather
than a light and dark pair. This was a deliberate call, stated as such
(`artifact-design` permits a single committed look when it is a choice, not
an omission): a formal analytical report reads better as a considered
printed-style document than as a console. Keep this choice unless a future
edition has a specific reason to add dark mode, and if it does, add it
properly (both `@media` and `[data-theme]` blocks) rather than half-doing it.

## Colour tokens

```css
--navy:#162646;        /* masthead, headings, primary ink for section titles */
--blue1:#385FAF;        /* accent, links, active states, timeline dots */
--blue2:#739BCF;        /* secondary accent, soft fills */
--copper:#C67C00;       /* caution / "found only by driving the page" flag, docs-only per house style */
--green:#27AE60;        /* resolved / confirmed / pass status */
--brick:#A6433D;        /* critical / blocking status - a restrained brick red, not a saturated alarm red */
--ink:#2C3E50;          /* body text, per Bluestaq house style */
--ink-soft:#5B6B80;     /* secondary/muted text */
--paper:#F6F4EE;        /* page ground - warm off-white, never pure white */
--card:#FFFFFF;         /* card and table-row surfaces */
--card-tint:#EFEDE4;    /* subtle recessed fills (chart tracks, nav pills) */
--hairline:#DEDACC;     /* card borders */
--hairline-strong:#C9C4B2; /* timeline rail, stronger borders */
--navy-tint:#EAEEF6;    /* info callouts, tag chips */
```

Categorical chart colours (the four defect-taxonomy slots), taken from the
`dataviz` skill's own validated default categorical set, slots 1, 3, 5 and 7
in that order. Validated all-pairs in light mode (worst all-pairs
normal-vision Delta E 16.3, OKLab x100; all other checks pass) using
`dataviz/scripts/validate_palette.js`:

```css
--cat-1:#2a78d6;  /* false-confidence tests */
--cat-2:#1baf7a;  /* browser-only / run-only defects */
--cat-3:#e87ba4;  /* fabricated or assumed values */
--cat-4:#4a3aa7;  /* gate / mirror lag */
```

Keep this order fixed across editions (the category each colour represents
must not change week to week) and never reuse `--green`, `--copper`, or
`--brick` as a fifth categorical slot: those are reserved for status, per
the dataviz skill's rule that status colours are never reused for series
identity. If a genuine fifth category is needed, re-run the validator
against a fifth slot before shipping it (do not eyeball it).

## Type

● Headings: **Spectral** (serif), weights 500 to 700.
● Body: **IBM Plex Sans**, weights 400 to 700.
● Data, code, file paths, version tags, stat figures: **IBM Plex Mono**.

Loaded via:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Spectral:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
```

## House style constraints (apply to every edition's copy, not just the first)

● UK English throughout the prose.
● No em-dashes or double dashes. Single hyphens are fine.
● No horizontal rule elements used purely as dividers. Separate sections
  with spacing and card/background boundaries instead.
● No "+" except where mathematically meaning addition. Use "and".
● Bullets are ● or ■, never a dash.
● Uncommon acronyms spelled out on first use; common software terms (API,
  CSS, UI, CI) do not need expanding for this audience, consistent with how
  `CLAUDE.md` itself is written.

## Layout shape

Single-column report, max content width ~900px, a slim navy masthead, a
sticky horizontal section-nav pill row beneath it, alternating full-width
sections separated by a hairline border (not a decorative rule, a genuine
section boundary), and these recurring components:

● **BLUF banner** — navy card, big headline, a 3-to-4-column stat grid.
● **Callout boxes** — four variants (`critical`, `warn`, `good`, `info`),
  each a tinted card with a coloured glyph and heading; used for anything
  that deserves to interrupt the reading flow.
● **Timeline** — a vertical rail of numbered dots connected by a line, a
  `turn` variant (brick-coloured dot) marking a point where a direction
  changed because of something Ash said rather than something a test found.
● **Instance cards** — a two-column grid of small cards, each tagged with
  where it was found (`this session`, `recorded in CLAUDE.md`, `found in
  browser`, `live UDL`), for the "core pattern" style section.
● **Bar chart** — plain HTML/CSS bars (no charting library needed), direct
  count labels inside each bar, using the four categorical colours in fixed
  order.
● **Stat comparison** — a two-panel before/after strip for any coverage or
  count delta worth calling out.
● **Do/don't** — two tinted columns, ✓ and ✕ row markers.
● **Recommendations** — numbered cards with a navy number badge and small
  tag chips (`code`, `process`, `github`, `people`, `memory`).
● **Decisions table** — a plain table, one row per decision, columns for
  question, decision, owner, and what it prevented.

Reuse the first edition's actual CSS wholesale (it already implements all of
the above, responsive to 400px, with focus-visible states) rather than
rewriting it from scratch each week. Only the content changes.
