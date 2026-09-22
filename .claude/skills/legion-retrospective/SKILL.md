---
name: legion-retrospective
description: Produce the weekly Legion process retrospective, an HTML report on what actually happened in the repository this week, honest about mistakes, decision changes, and their impact on the build. Use this skill when asked to "run the retrospective", "weekly retrospective", "Legion retrospective", or when a scheduled Friday trigger fires it. Also use when asked to review this project's own working process, learn from recent sessions, or safeguard future conversations against a recurring failure mode. Never fabricate a finding to fill a quiet week; a week with nothing to report says so. Always verifies the checkout is real (CLAUDE.md and src/ present, on the right branch) before trusting anything in it, and repairs and reports a bad checkout rather than reporting on an empty repository.
---

# Legion retrospective

A weekly, evidence-only report on how work on Legion actually went: what broke,
what was found and how, what was decided and by whom, and what to change so it
does not repeat. Modelled on the retrospective run on 14 to 15 September 2026,
whose headline finding was that ten green App Store stages and 96% coverage
said nothing about whether `/udl/elset` actually worked, because nothing in
the pipeline calls real UDL.

**The standard this skill is held to is the same one it reports on.** Every
number in the output must trace to a command run this session, not to memory,
not to what "usually" happens, and not to last week's report copied forward.
If a claim cannot be traced to something read, run, or diffed this session,
it does not go in the report. This is not a stylistic preference; it is the
exact failure mode the first retrospective exists to name.

## When this runs

● On the Friday schedule (see the Routine set up alongside this skill), in a
  fresh session with no memory of prior weeks. Everything below has to work
  from the repository alone.
● On request, at any time, for the trailing seven days or a stated window.

## Step 0: prove the checkout is real before trusting anything in it

Found the hard way on 21 September 2026: a persistent session's working
directory silently reverted to a bare, two-commit clone (the repository's
`main`, `README.md` only, no `src/`, no `CLAUDE.md`) between one week's work
and the next. Nothing announced this. The only signal was the project's own
instruction file no longer being present at session start. A retrospective
run against that checkout would have produced a fully-formatted, entirely
hollow report and had no way of knowing it.

Before Step 1, run:

```bash
cd /home/user/Legion
git branch --show-current
git log --oneline -3
test -f CLAUDE.md && test -d src && echo "checkout looks real" || echo "checkout is NOT what it should be"
```

If `CLAUDE.md` or `src/` is missing, or the branch or log does not match what
the previous week's edition reported, **do not proceed to Step 1.** Instead:

```bash
git fetch origin
git checkout claude/fastapi-handoff-review-21n93l   # or whatever branch main development is on
git reset --hard origin/claude/fastapi-handoff-review-21n93l
```

then re-run the check above to confirm it now passes. Record in the report,
plainly, that this happened: what was found missing, and that the checkout
was repaired before the rest of the evidence was gathered. This is itself a
category 2 incident (a run-only defect, invisible until something actually
tried to read the file) and belongs in that week's taxonomy count, not
swept aside as tooling noise.

If the repair itself fails (the branch is gone, the remote is unreachable),
stop and report that plainly rather than publishing anything. A retrospective
that cannot verify its own evidence is not a quiet week; it is no report.

## Step 1: fix the window

Default window is the trailing seven days from now. If asked for a different
range, use that instead. State the window in the report itself, in plain
language ("8 to 15 September 2026"), because a reader needs to know what is
and is not covered.

## Step 2: gather evidence for real

Read `references/evidence-checklist.md` and run every command in it before
writing a word of the report. Do not reason about what probably happened;
read the actual git log, the actual test output, the actual coverage
numbers, the actual diff of `CLAUDE.md`. This mirrors the project's own
"never assume anything, check it for real" standing instruction, applied to
the act of reporting on the project rather than to the project's code.

If a check cannot be run (no network, no live UDL, a tool unavailable),
say so in the report as `UNKNOWN`, the same marker this project already uses
elsewhere. Do not silently omit it and do not guess a plausible value.

## Step 3: classify what happened against the standing taxonomy

Four categories were established in the first retrospective, chosen because
each names a distinct mechanism, not a distinct symptom:

1. **False-confidence tests** — a test or guard passed without examining the
   real thing (a mocked layer, a `response_model` that stripped the field
   under test, an error body read for the wrong reason, a migration test
   comparing a file with itself).
2. **Browser-only or run-only defects** — invisible to every contract test
   because they only manifest when the thing actually executes (a
   double-declared identifier that throws at parse time, a CSS cascade
   collision, a token name collision).
3. **Fabricated or unconfirmed values reported as fact** — a hard-coded
   status, an assumed ordering, a swallowed failure re-labelled "expected".
4. **Gate or mirror lag** — a Code Quality or Dependency Scanning finding the
   platform reports before the local mirror knows to check for it.

Use these four unless something this week genuinely does not fit any of
them. If that happens, add a fifth and say plainly that the taxonomy grew
and why, the same way `docs/SONAR-RULE-REGISTER.md` records a new rule the
moment the platform fires it rather than on a guess. Do not force an
awkward fit into an existing category to avoid growing the list.

**A quiet week is a valid result.** If nothing this week matches any
category, the report says that in one sentence and moves on to the smaller
sections (decisions, coverage deltas, what shipped). It does not manufacture
a finding to avoid an empty section. An invented finding is itself an
instance of category 3.

## Step 4: build the report

Load `artifact-design` and `dataviz` before writing any HTML, exactly as the
first retrospective did. Then read `references/design-system.md` and reuse
its tokens, fonts, and validated categorical palette **unchanged** rather
than re-deriving or re-validating them. This is the same discipline this
codebase already applies to its own product palette: it was validated once,
it is documented, and it is reused rather than re-picked. Re-run the
dataviz palette validator only if a new categorical series is added beyond
the four already validated.

Structure (adapt section presence to what the week actually produced; do
not force every section to be non-empty):

● **BLUF banner** — the week's bottom line in two or three sentences, plus
  three or four headline stats, each traced to a command from Step 2.
● **Headline finding** — only if one incident this week clearly outweighs
  the rest. If not, omit this section rather than inflating something
  ordinary into a headline.
● **Timeline** — the week's commits and decisions in order, numbered
  because it is a genuine sequence.
● **Defect taxonomy** — the bar chart, using the four validated categorical
  colours in fixed order, direct-labelled with counts. Only categories with
  at least one instance appear.
● **Decisions that held** — any named `[DECISION - Ash]` resolved this week,
  or any other explicit decision recorded in `CLAUDE.md`'s diff.
● **What already works** — credit for safeguards that caught something
  before it shipped. A retrospective that only lists failures is not
  reporting the whole picture.
● **Do & don't** — short, drawn only from this week's actual incidents, not
  copied forward from a previous edition.
● **Recommendations** — numbered, priority order, each tagged with what kind
  of change it is (`code`, `process`, `github`, `people`, `memory`).
● **Where more would have helped** — honest, specific, and only when the
  record actually supports it. Do not manufacture self-criticism to seem
  balanced; say plainly when the week was executed well.

## Step 5: publish

Publish as a new Artifact (do not update a previous week's edition; each
week is its own dated issue, the same convention this organisation already
uses for its recurring HTML briefings). Title format: `Legion Retrospective,
<D Month YYYY>` (the Friday date the report covers up to). Favicon 🛰️, icon
`report`. One-sentence `description` naming the week's headline in plain
words, or "a quiet week" if Step 3 found nothing.

## Step 6: report back

After publishing, send a short summary (three to five sentences) with the
artifact link. If notifications are configured on the Routine, this reaches
Ash automatically; do not assume it has been read and do not repeat the
full report in chat.

## Standing rule this skill must not violate

Never let this skill's own report become an instance of category 1 (a check
that passed without looking). If in doubt about whether a figure is real,
run the command again rather than trust a number carried over from
`references/` or from a prior week's memory. `references/design-system.md`
holds presentation values only (colours, fonts, section shape); it never
holds a substantive number, count, or finding. Those come from Step 2, every
time.
