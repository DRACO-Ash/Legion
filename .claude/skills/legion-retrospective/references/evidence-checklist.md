# Evidence checklist

Run every command below (adjusting the `--since` window per Step 1) before
writing anything. This is what "check it for real" means for this skill,
concretely. If a step fails or cannot run, record it as `UNKNOWN` in the
report with the reason; do not skip it silently and do not substitute a
guess.

## 1. What actually shipped this week

```bash
cd /home/user/Legion
git log --since="7 days ago" --date=short --pretty=format:"%ad %s"
git log --since="7 days ago" --oneline -- src/VERSION | wc -l   # version bumps
cat src/VERSION                                                 # current version
```

## 2. Test health, before trusting any coverage claim

```bash
.venv/bin/python -m pytest -q 2>&1 | tail -5
.venv/bin/python -m pytest -q --cov=src --cov-report=term-missing 2>&1 | tail -30
```

Compare this week's pass count and coverage percentage against the previous
edition's reported numbers (read the previous week's published artifact if
its URL is known, via `Artifact` with `action: "read"`; otherwise state that
no prior edition was available for comparison rather than inventing one).

## 3. The local gate, read in full, never tailed

```bash
./scripts/check-quality-gate.sh 2>&1
```

Read the whole output. Piping this through `tail` or `head` is the exact
mistake `CLAUDE.md` already records as a cost this project has paid once;
do not repeat it in the one skill whose entire job is to catch this pattern.

## 4. What changed in the project's own memory

```bash
git log --since="7 days ago" -p --date=short -- CLAUDE.md
```

Read the actual diff. A new `## ` heading or a new `[DECISION - Ash]` line
is worth surfacing in "Decisions that held". A line that only rewords an
existing point without changing the underlying rule is not a decision and
does not belong there.

## 5. Sonar gate history this week

```bash
git log --since="7 days ago" -p --date=short -- docs/SONAR-RULE-REGISTER.md
```

Any new row is a gate-or-mirror-lag incident (category 4) if it records a
finding the platform reported before a local mirror existed for it.

## 6. Release and packaging health

```bash
git tag | tail -5
git ls-remote --tags origin 2>&1 | tail -5
```

If local tags exist that are absent from `git ls-remote --tags origin`,
the tag-push gap recorded in the first retrospective is still open. State
its current status plainly (open, partially resolved, or resolved) rather
than assuming last week's finding still holds.

## 7. Live UDL state, only if a check was actually run this week

Do not run `scripts/udl_live_check.py` from this skill on its own initiative
against real UDL credentials; it makes live calls that count against a real
budget and need the same care CLAUDE.md already documents. Only report on
UDL live-check results if Ash has run one and shared its output during the
week, or if evidence of one exists in a committed file (`git log --since
"7 days ago" -- '*udl-evidence*.json'` or similar). Otherwise state plainly
that no live UDL check ran this week.

## 8. Open decisions and pending work

```bash
grep -n "\[DECISION - Ash\]" CLAUDE.md
grep -n "^\s*●\|^\s*\*\*Still" READINESS.md
```

Anything still open here is worth one line in the report if it has been
open for more than one week, so a standing question does not silently age
out of view.

## 9. What this session's own gate found, if any code changed

If this week's window includes source changes, run the calibration check
described in `SKILL.md` Step 3 before crediting a new guard: has anything
this week been proven to fail, by name, against the defect it targets, with
that defect restored on purpose? If nobody did that this week, say so; do
not assume the calibration discipline was followed just because a test was
added.
