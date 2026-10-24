# Core #237 — Slice 6: Installed candidate qualification and handoff

**Issue:** [#237](https://github.com/Paper-Data-Suite/pds-core/issues/237) · **Umbrella:** [#235](https://github.com/Paper-Data-Suite/pds-core/issues/235)
**Design authority:** [Accepted v1 contract](../teacher_experience_contract_v1.md), [ADR 0005](../decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md) and [conformance vectors](../teacher_experience_conformance_v1.md)
**Status:** Executable qualification **procedure** and candidate acceptance boundary; the source document does not itself prove a run, a published Core release, or a consumer adoption.

## 1. Exactly what this issue delivers

Core #237 adds only these public teacher-experience surfaces:

- `pds_core.teacher_experience.TEACHER_EXPERIENCE_CONTRACT_VERSION == "1"` and `get_teacher_experience_capabilities()`.
- `pds_core.teacher_ui.TeacherScreenHeader`, `render_teacher_header` and `print_teacher_header`.
- `pds_core.teacher_commands.PromptKind`, `SharedTeacherCommand` and `parse_shared_teacher_command`.

The exact advertised candidate-source capabilities are `terminal.header.v1` and `terminal.notes_command.v1`. The parser **recognizes a request**, not a working Notes utility. Neither `pds_core.teacher_context` nor `pds_core.teacher_menus` is introduced by #237; no Notes records, `pds-core notes` routes, roster edits or callable classroom menu exist yet. The published Core **0.6.6 release** predates these source changes. Reusing the version `0.6.6` when building a disposable development candidate is **not** publication or qualification of a new v0.6.6 release artifact.

## 2. Executable, isolated candidate acceptance (D2)

`scripts/verify_issue237_installed_teacher_terminal.py` is a standard-library-only executable acceptance script. Run with the Python from the **isolated virtual environment into which the built wheel was actually installed**, under `python -I`, with the working directory **outside the source checkout**. Its required inputs are:

- `--source-checkout` — exact checkout directory that **must not** be the installed package's import source.
- `--expected-version` — parsed from the candidate's `pyproject.toml` (currently `0.6.6`, not a new published release).
- `--wheel` — actual wheel installed into the test environment.
- `--report` — a new JSON file outside the checkout, containing the wheel SHA-256, platform/Python, import origin, capability tokens and executed smoke-case names.

The script checks actual installed distribution/module origins; accepted v1 contract version; *exactly* the two permitted capability strings; no Notes/admin modules or capabilities; exact public exports; plain/green two-/three-line rendering; captured-output and `NO_COLOR` fallback; rejection of unsafe header input; only-eligible exact `:notes` recognition; ineligible fields, opt-out, noninteractive and near-miss cases; unchanged Core `B/M/Q`, optional `A`, Quillan-like `N/W`; and installed `core --help` / `pds-core --help` console entry points. It must leave the external smoke directory unchanged. **No student or teacher data is used.**

The Slice 6 guarded runner builds a candidate wheel in an isolated temporary output folder, installs the *exact built wheel* into a fresh venv **without index/dependencies**, runs the verifier, records its SHA-256 and executes the existing full project suite before staging. A failed test, wheel install, CLI probe, conformance check, source drift, or unqualified capability stops the runner **before commit/push**. It leaves the report in the runner's temporary evidence directory only for the duration of qualification; the console prints the candidate SHA/OS/Python evidence.

The repository CI package-smoke job invokes the same script against its separately installed **Ubuntu 3.11** candidate wheel and uploads its JSON evidence. A separate **Windows 3.11** installed-wheel CI job repeats that test and uploads its own JSON evidence. Existing matrix validation on Windows/Ubuntu Python 3.11–3.14 and released-consumer compatibility remain in force. CI job conclusions and artifact hashes must be quoted from actual runs in the PR; this document does **not** mark them passed in advance.

## 3. Traceability and exclusions

| Accepted family | #237 evidence | Remaining owner/qualification |
| --- | --- | --- |
| H01–H05, H09 | Source tests and isolated wheel smoke: exact header/validation/green bytes/injected stream | Real adopter screen behavior: D3 |
| H06–H08 | Source-controlled stream and Windows VT/ANSI fallbacks; installed captured-stream/`NO_COLOR` | Physical Windows ARM64 green-console acceptance: #244/D4 |
| H10–H11 | Presentation-only hints, no data lookup; Windows and Ubuntu installed candidate checks | Actual authorized producer context and classroom hardware: D3/D4 |
| C01–C09 | Comprehensive source parser tests plus installed exact-token/flags/field tests | None for the *pure Core parser*; producer dispatch remains separate |
| C10–C13 | Synthetic Quillan-like `N/W`, existing `B/M/Q`, local choice and absent Notes-menu capability | Exhaustive producer-specific prompt census, installed adopter and real Notes-menu flows: #238–#240/D3 |
| R01–R12, P01–P12 | Explicitly **not claimed** in #237 | Core #238–#244, Suite #51 and producers |

This work creates no global input hooks, new `NavigationChoice` variant, public Notes menu, producer package edits, Suite teacher home, workspace/private-store mutations, novel CLI aliases, new runtime dependencies or migration requirements.

## 4. PR acceptance and deployment boundary

- [ ] Source full `python -m pytest`, `python -m ruff check .`, `python -m mypy .` and `git diff --check` pass at the exact final commit.
- [ ] The guarded local candidate smoke completes from outside the checkout with an **actual wheel** and explicit SHA-256/OS/Python evidence.
- [ ] The PR's **Ubuntu and Windows installed candidate-wheel** checks pass; upload artifacts document both environments.
- [ ] The unchanged full validation matrix, existing Core menus/CLI, build smoke and released-consumer compatibility all pass.
- [ ] PR reviews exact frozen imports/signatures, no Notes/admin capability advertisement, no input-loop takeover, and no unexpected production/schema changes.
- [ ] PR body contains **`Closes #237`**. Only after CI and review: squash merge, reconcile `main`, and record the exact merged commit.

**Release decision is separate:** this issue does not silently publish a new Core version or override the immutable published 0.6.6 artifact. Consumers should use a **future explicitly tagged, D2-qualified release** with exact compatible dependency bounds, plus their own D3 adoption checks. Core #244/Suite remain responsible for broader D4 and physical Windows ARM64 qualification.
