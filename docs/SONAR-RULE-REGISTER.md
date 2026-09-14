# SonarQube rule register

Every rule the Bluestaq App Store's Code Quality gate has actually fired
against this repository, the upload that reported it, and the local check
that now catches it.

**Read this before writing code, and run `scripts/check-quality-gate.sh`
before packaging.** The gate's only visible message is "Quality Gate FAILED",
so a rule that is not in here costs an upload cycle to discover. A rule that
is in here costs nothing.

## The analysis reaches `scripts/`, whatever the properties file says

The most expensive thing the 0.15.2 upload taught, and the reason nine of its
fourteen findings were invisible here: **`sonar-project.properties` sets
`sonar.sources=src`, and the platform reported issues in
`scripts/check-quality-gate.sh` and `scripts/udl_live_check.py` anyway.**

That is a FACT from a job report, not a theory about the scanner. Every mirror
in this repository had read that property and scanned `src` and `tests`, so a
shell script added the day before went to the platform completely unchecked
and produced six findings on its own.

Every mirror that walks a tree now walks `scripts/` too, and
`test_scripts_are_scanned_by_every_mirror_that_walks_a_tree` fails if somebody
narrows the set back on the strength of the properties file.

**`scripts/` is still outside `ruff check src tests`, and that is still
deliberate**, for the reason `CLAUDE.md` gives: the credentials loader is
copied verbatim from the Script mode skill. Sonar analysing a tree and ruff
linting it are separate questions, and the answers differ.

## The rule for this register

● **A rule goes in the moment the platform reports it**, never on a guess
  about what Sonar might dislike.
● **It is calibrated against the upload that reported it**: added first,
  confirmed to fire on the unfixed code at the place the platform named, and
  confirmed not to fire anywhere else. Only then is the code changed.
● **A mirror that over-fires is a defect.** The input-label check flagged a
  correctly wrapped `<label><input></label>` on its first run. The platform
  does not report that, so the mirror was corrected rather than the markup.
  A register full of false positives is one nobody reads.
● **It never comes out.**

## Why the register exists

The 0.15.0 upload reported **eighteen new issues across eight rules**, and
every local check passed. The mirrors were not wrong; they only ever covered
the rules something had already been caught by. The set has to grow every
time the platform finds something new, and it has to be written down
somewhere a person will look.

## The rules

| Rule as the platform words it | First reported | Where it fired | Local check |
|---|---|---|---|
| Define a constant instead of duplicating this literal | 0.4.7 | `seed_data.py`, 26 findings | `test_sonar_contracts.py::test_no_duplicated_string_literals` |
| Use `logging.exception()` instead | 0.4.7 | `logger.error` inside `except` | `test_sonar_contracts.py::test_error_logging_inside_a_handler_uses_exception` |
| Refactor this function to reduce its cognitive complexity | 0.4.8 | reproduced the platform's 25 and 18 exactly | `test_sonar_cognitive_complexity.py` |
| Extract this nested ternary operation | 0.9.0 | `index.html`, inside a `${...}` slot | `test_sonar_contracts.py::test_no_nested_ternary_operations` |
| Refactor this code to not use nested template literals | 0.9.0, again 0.15.0 | `index.html` | `test_sonar_platform_rules.py::test_no_nested_template_literal_anywhere_in_the_script` |
| Use `.dataset` rather than `getAttribute("data-...")` | 0.7.0 | `index.html` | `test_sonar_contracts.py::test_data_attributes_are_read_through_dataset` |
| An async call at module top level must be awaited | 0.7.0 | `index.html` | `test_sonar_contracts.py::test_the_start_up_fetches_are_awaited` |
| Duplicate CSS selector | 0.7.0 | `index.html` | `test_sonar_contracts.py::test_no_selector_is_declared_twice` |
| Use a `Set` for a membership test | 0.7.0 | `index.html` | `test_sonar_contracts.py::test_a_membership_test_uses_a_set` |
| Refactor this exception test to have only one invocation | 0.11.0 | `test_compendium_models.py` | `test_sonar_contracts.py::test_an_exception_test_makes_one_call_that_can_throw` |
| Add path parameter "X" to the function signature | 0.15.0 | `object_lists.py`, 10 findings | `test_sonar_platform_rules.py::test_a_route_path_is_a_literal_string` |
| Use `Annotated` type hints for FastAPI dependency injection | 0.15.0 | `operability.py` | `test_sonar_platform_rules.py::test_fastapi_parameters_use_annotated` |
| Associate a valid label to this input field | 0.15.0 | `index.html`, the palette input | `test_sonar_platform_rules.py::test_every_input_carries_a_label` |
| Use `<dialog>` instead of the dialog role | 0.15.0 | `index.html`, the palette overlay | `test_sonar_platform_rules.py::test_no_element_fakes_a_dialog_with_a_role` |
| Non-interactive elements should not be assigned interactive roles | 0.15.0 | `index.html`, the results list | `test_sonar_platform_rules.py::test_no_non_interactive_element_wears_an_interactive_role` |
| Use `<datalist>` or `<select>` instead of the listbox role | 0.15.0 | `index.html`, the results list | same check as above |
| "tabIndex" should only be declared on interactive elements | 0.15.0 | `index.html`, the briefing `<pre>` | `test_sonar_platform_rules.py::test_tabindex_only_on_interactive_elements` |
| Prefer `.some(…)` over `.find(…)` | 0.15.0 | `index.html`, graph list | `test_sonar_platform_rules.py::test_find_is_not_used_as_a_boolean_test` |
| Use '[[' instead of '[' for conditional tests | 0.15.2 | `check-quality-gate.sh`, 4 findings | `test_sonar_platform_rules.py::test_shell_conditionals_use_double_brackets` |
| Add an explicit return statement at the end of the function | 0.15.2 | `check-quality-gate.sh`, the `run` helper | `test_sonar_platform_rules.py::test_shell_functions_return_explicitly` |
| Assign this positional parameter to a local variable | 0.15.2 | `check-quality-gate.sh`, the `run` helper | `test_sonar_platform_rules.py::test_shell_functions_name_their_positional_parameters` |
| Replace this comprehension with passing the iterable to the dict constructor | 0.15.2 | `udl_live_check.py` | `test_sonar_platform_rules.py::test_no_dict_comprehension_merely_copies` |
| Use asynchronous features in this function or remove the `async` keyword | 0.15.2 | `object_lists.py`, 4 findings | `test_sonar_platform_rules.py::test_no_route_handler_is_async_without_awaiting` |
| LLMs running this code with faulty CLI arguments can escape file system restrictions (Vulnerability) | 0.15.2 | `udl_live_check.py`, the `--out` flag | `test_sonar_platform_rules.py::test_a_caller_supplied_path_is_checked_before_it_is_written` |
| Merge this if statement with the enclosing one | 0.15.3 | `bump_version.sh`, the coverage warning | `test_sonar_platform_rules.py::test_no_shell_if_wraps_only_another_if` |

## The two things a mirror cannot catch

Both are Code Quality gate conditions, and neither is a rule:

● **Duplicated lines on new code.** There is no local check. Shared fixtures
  live in `tests/conftest.py` for this reason.
● **Security hotspots reviewed.** If this is the failing condition, no upload
  will fix it. A person reviews them in the SonarQube interface.

And one that is a process condition rather than a rule: **coverage must be
measurable**, which means a release has to change a Python file under
`sonar.sources`. `bump_version.sh` and `scripts/package.sh` both refuse a
release that would not; `--allow-unmeasurable` overrides the bump.

## Known blind spots, recorded rather than hidden

● The nested-template check scanned **line by line** until 0.15.0, so a
  nesting spread across three lines passed. It now scans the whole script.
  Any check written against a single line has this weakness by construction.
● **The `.find()` mirror missed the same rule twice.** Written at 0.15.0 from
  the one instance in front of it, a `.find()` wrapped in `(… || {})`, it went
  green while 0.15.2 reported a second instance that bound the result to a
  name and then wrote `if(record)`. A mirror written from an example covers
  the example. It now asks the rule's own question: is the found item ever
  actually read? Calibrated against the two legitimate `.find()` calls in the
  same file, where it is.
● **A rule reported in one file is usually latent in twenty.** The gate counts
  new issues, so the four async handlers it named were simply the four in the
  file that changed; twenty-two more carried the identical shape and thirteen
  single-bracket conditionals sat in two older shell scripts. All were fixed,
  because each one was a gate failure waiting for its file to be edited. When
  a mirror fires far beyond what the platform reported, that is usually the
  mirror being right, not wrong.
● The duplicated-literal check has a `MIN_LENGTH` floor of 5, added when it
  began flagging a bare `" "` inside f-strings. That floor is SonarQube's own
  default and sits below the shortest literal the platform has reported here
  ("4 years", seven characters), but it is a judgement and it is recorded.

## Fixing a finding can produce the next one

0.15.3 reported a single issue, and it was in a line 0.15.2 had just changed:
the nested `if` in `bump_version.sh` had been there all along, but converting
its inner test from `[` to `[[` made the block new code, so the enclosing-`if`
rule counted for the first time.

Nothing went wrong here, and the fix was a one-liner. It is recorded because
it is the shape to expect: **touching a file exposes every latent rule in the
lines you touch.** A first upload after a long quiet period will find more
than the change itself warrants, and the way through is to keep fixing rather
than to conclude the mirrors are failing.

## One mirror is deliberately narrower than its rule

`test_no_route_handler_is_async_without_awaiting` scans `src` only, while
every other Python mirror scans `src`, `tests` and `scripts`.

The async test doubles in `tests/conftest.py` stand in for the UDL client's
async interface and are awaited by the code under test, so they must stay
`async` and cannot be fixed. The platform has only ever reported this rule in
`src/routes/`. A mirror demanding an unfixable change is worse than no mirror,
so the scope follows the evidence. If the platform ever reports it against a
test double, that is a new entry here and a genuinely different problem.

## Fixing a smell can introduce a defect

Recorded because it nearly happened, and because "the gate asked for it" is
not a safety argument.

Dropping the redundant `async` keyword is the fix SonarQube names, and it is
correct: an `async def` handler doing blocking file I/O holds the event loop.
But it also moves every handler into a threadpool, where they genuinely run at
once. Every write in `src/store.py` is read-modify-write, `os.replace` makes
only the write itself atomic, and nothing held a lock. Two concurrent edits
would both answer 200 and one would vanish.

Proved rather than assumed: with the lock removed on purpose, twelve
concurrent updates lost ten of themselves.
`tests/test_store.py::test_concurrent_updates_do_not_lose_each_other` holds
it, and twelve concurrent PATCHes against a real running server confirmed it
end to end.

**Before applying a mechanical fix across a codebase, ask what property the
old shape was providing by accident.**

## Settled by 0.15.4: the route factory is outside the rule

Carried as INFERENCE since 0.15.2: whether registering routes with
`add_api_route` and literal paths avoids "a route path should be a literal
string", which is written against the decorator form.

It does. `src/routes/object_lists.py` gained 33 lines in 0.15.2, so the
registrations were analysed as new code. The rule did not fire in that
upload's fourteen findings, nor in 0.15.3, nor in the clean 0.15.4. **All ten
stages passed on 0.15.4 and Code Quality was among them**, which is the first
time that gate has ever passed for this application.
