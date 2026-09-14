# SonarQube rule register

Every rule the Bluestaq App Store's Code Quality gate has actually fired
against this repository, the upload that reported it, and the local check
that now catches it.

**Read this before writing code, and run `scripts/check-quality-gate.sh`
before packaging.** The gate's only visible message is "Quality Gate FAILED",
so a rule that is not in here costs an upload cycle to discover. A rule that
is in here costs nothing.

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

## The two things a mirror cannot catch

Both are Code Quality gate conditions, and neither is a rule:

● **Duplicated lines on new code.** There is no local check. Shared fixtures
  live in `tests/conftest.py` for this reason.
● **Security hotspots reviewed.** If this is the failing condition, no upload
  will fix it. A person reviews them in the SonarQube interface.

And one that is a process condition rather than a rule: **coverage must be
measurable**, which means a release has to change a Python file under
`sonar.sources`. `bump_version.sh` warns when a release would not.

## Known blind spots, recorded rather than hidden

● The nested-template check scanned **line by line** until 0.15.0, so a
  nesting spread across three lines passed. It now scans the whole script.
  Any check written against a single line has this weakness by construction.
● The duplicated-literal check has a `MIN_LENGTH` floor of 5, added when it
  began flagging a bare `" "` inside f-strings. That floor is SonarQube's own
  default and sits below the shortest literal the platform has reported here
  ("4 years", seven characters), but it is a judgement and it is recorded.
