# Core #236 — Slice 4: Design traceability, adoption handoff and qualification evidence

**Status:** Contract-documentation release candidate for review; **not** implemented/installed acceptance
**Core issue:** [#236](https://github.com/Paper-Data-Suite/pds-core/issues/236), under [#235](https://github.com/Paper-Data-Suite/pds-core/issues/235)
**Contract ID:** `pds_core.teacher_experience/1` — [`teacher_experience_contract_v1.md`](../teacher_experience_contract_v1.md)
**Conformance:** [`teacher_experience_conformance_v1.md`](../teacher_experience_conformance_v1.md)
**Architecture:** [ADR 0005 — Accepted architectural decision](../decisions/0005-adopt-versioned-teacher-experience-public-interfaces.md)

## 1. Source and authority record

| Evidence | Exact baseline read during #236 | Interpretation |
| --- | --- | --- |
| Core `main` before #236 | `bf3e6c08dd3f51e47cdbe56b11a3873a9d4491b3` | pds-core **0.6.6** public APIs; no contract-v1 implementation |
| Core issue branch after Slice 1 | `d20d77a` | Audited source and prompt boundaries; **sample**, not census |
| Core issue branch after Slice 2 | `aec77934240cfb6a47471bcdbeb483e644caecab` | Proposed v1 header/command/capability shapes and ADR 0005 |
| Core issue branch after Slice 3 | `1df7e6d10b558f8e9e42d5dfa58db0d3baeca05b` | Proposed v1 context, menu, outcome/return, custody, CLI parity seams |
| Suite design specification v0.2 | [development branch](https://github.com/Paper-Data-Suite/pds-paper-data-suite/blob/49-evergreen-launch-and-supported-composition-upgrades/docs/design/teacher-experience-design-specification.md), head `4d23f16b8d3fb9f24eaf209b6a7aee24d3bca5b5` | Owner-accepted D-01–D-08 design **only**, not Suite released conformance |
| All seven consumer repositories | Commit-pinned ScoreForm/Quillan/Concord/Meridian/Vitrine/Portia and Suite refs in [Slice 1 audit](issue-236-slice1-teacher-experience-baseline.md) | Current source observations, not exact installed consumer qualification |

Core #236 is a **source-documentation freeze**. The only currently usable baseline APIs are the existing Core v0.6.6 symbols identified in the audit. New v1 names, menu actions, private Notes data, version/capability reporting and runtime guard behavior are **specified but not importable**. No new minimum Core release can yet be named for any new v1 feature. Core remains independent of Suite and producers; Suite retains its teacher-home, launcher/trust and whole-product UX responsibilities.

## 2. Traceability: eight accepted Suite decisions

| Decision | What Core contract v1 freezes | Proof required *after* #236 |
| --- | --- | --- |
| **D-01** — Notes & Tasks; Idea / Task / Reflection | Contract §§2.1/4.5; menu capability; category boundary | #238–#240 data/service/menu, P04/P05; UX-02/03 |
| **D-02** — Core workspace-associated collection, OS-user protection and single-user limit | §4.1 hint versus identity, §4.5 custody, `notes.records.v1` | #238 stable association and threat model; #243 portability; P01–P03, P08/09; UX-10 |
| **D-03** — exact menu-choice `:notes`, preserve Quillan N/W | §2.3 pure opt-in parser and §3 compatibility | #237 test vectors C01–C13; each consumer's complete adopted-menu audit; UX-02 |
| **D-04** — green identity/title/optional context, no compact preference | §2.2 renderer and capability policy | #237 H01–H11 including Windows/ARM64, streams and `NO_COLOR`; UX-01 |
| **D-05** — one in-process Core admin menu and caller revalidation | §§4.1–4.4; `classroom.menu.v1` | #241–#242 guarded service and menu, R01–R12/P10; UX-06 |
| **D-06** — no structured student references in initial Notes | §4.1 prohibited hint metadata and §4.5 custody | #238–#240 schema/attempted-link tests, P05/P06; UX-10 |
| **D-07** — personal Tasks distinct from producer attention | §§2.1/4.5; `paper_data_suite.module_operations` remains separate | #239 task semantics; Suite #51 separate headings/provenance, P07; UX-12 |
| **D-08** — Suite UX/teacher home; Core primitives/admin/Notes; gradual producer adoption | §§1/3/5 and ADR ownership decision | Core #237–#244, Suite #51/#15, producer tests; no double implementation of Concord #139 work |

## 3. Traceability: Suite specification sections and 12 UX scenarios

| Suite v0.2 section / scenario(s) | Contract / evidence | Ownership / gate |
| --- | --- | --- |
| §3 principle of teacher-first screens | contract §1/§3; ADR rationale | Suite and producers adapt; not accomplished by new Core UI APIs alone |
| §5 headers | contract §2.2; **H01–H11** | Core #237 then consumer screens; UX-01 |
| §6 B/M/Q, `:notes`, context | contract §§1/2.3/4.1–4.4; **C01–C13, R01–R12** | #237, #240 and adopting callers; UX-02/06 |
| §7 guided choice/review/confirm/commit/report/continue | contract §§4.2–4.4; **R07–R10, P10/P11** | Core service owners and each producer; UX-04/05/08/09 |
| §8 Notes & Tasks, categories, private storage, local owner, personal queue | contract §§2.1/4.5; **P01–P09** | Core #238–#240/#243; UX-02/03/10/12 |
| §9 Workspace & Classroom Management | contract §§4.3/4.6; **R11, P10–P12** | Core #241–#242 and callers; UX-06 |
| §10 Suite teacher home and launch | contract §§1/3/4.6; separate trust boundary | Suite #15/#51/#49; UX-07 |
| §11 producer integration, journeys and canonical authority | contract §§3/4.4/5, [Slice 1 audit](issue-236-slice1-teacher-experience-baseline.md) | Producer-local adoption; UX-04/05/09/11 |
| §12 UX-01–UX-12 | [complete owner mapping](../teacher_experience_conformance_v1.md#6-specification-level-teacher-journeys-ux-01ux-12) | D1–D4 gates not completed in #236 |
| §13 staged implementation/dependency order | contract §5; §4 below | Core #237–#244, Suite #51 and producers |
| §14 decisions and qualification gates | decision matrix §2; [conformance](../teacher_experience_conformance_v1.md) | Design accepted; code/security/artifacts unqualified |
| §15 adoption and change control | contract §3; ADR 0005 | Owner review of public semantics, additive evolution and release-level acceptance |

**Important distinction:** The original specification permits displaying a validated student label **inside an owning producer's screen**. That is **not** consent to copy any student identity or student-specific context into shared Notes metadata. The header's application label is likewise **not** a trusted installed-module identity. Both boundaries are preserved in the contract and must be tested by consumer adopters.

## 4. Issue handoff and sequencing (no new work hidden in #236)

| Next owner | Implement or adopt | Dependency / qualification stop |
| --- | --- | --- |
| **Core #237** | `pds_core.teacher_experience`/`teacher_ui`/`teacher_commands`, pure parser, safe streamed headers | First production code after #236; H/C vectors, 0.6.6 navigation compatibility. No Notes service promised |
| **Core #238** | Stable private workspace/OS-user association and threat model | No synthetic owner identity from actor label; private data location/isolation tested before enabling Records |
| **Core #239** | Guarded Notes & Tasks record models, storage, query and lifecycle | Idea/Task/Reflection and revisions; no structured student links or automatic module mutation |
| **Core #240** | In-process Notes menu plus direct `pds-core notes` CLI | Same Core services and guarded semantics; `notes.menu.v1` must not precede qualified `notes.records.v1` |
| **Core #241** | Guarded individual roster preview/commit and direct CLI | Reuse existing Core rosters/roster-import safeguards; stale-write refusal |
| **Core #242** | Callable in-process Workspace & Classroom Management and same Core menu/CLI authority | Depends on #241, caller revalidation, no subprocess menu or parallel roster authority |
| **Core #243** | Explicit private Notes portability, backup, transfer and restore | Ordinary workspace backup exclusion truthful; no implicit sync |
| **Core #244** | Integrated conformance and exact installed release qualification | Full D1/D2 proof, eligible capability tokens, failure/partial paths and cross-platform acceptance |
| **Suite #51 / #15** | Adopt v0.2 design, implement Suite home and Core menu entry points, maintain launcher context | Suite #49 independently controls installed trust/evergreen launching; `pds` CLI and module-operations providers remain separate |
| **ScoreForm** | Screen header/choice opt-in, safe classroom handoff and stale assignment/roster revalidation | Full assignment/scoring/scan nested-screen audit and installed qualification |
| **Quillan** | Review return from Notes, current work revalidation and safe command integration | Preserve **N/W**, student review free text, confirmed draft durability; no N Notes alias |
| **Concord #139 / #153** | Integrate supported UI/command without duplicating existing assessment/grouping UX work | Existing activity/assessment/group/packet workflows retain domain authority |
| **Meridian #120 / #123** | Integrate shared UI/menus around existing Grades/evidence safeguards | Do not replace Grade/authorization/attempt semantics with shared presentation abstractions |
| **Vitrine** | Safe portfolio/subject/profile/attention screen integration | Confirm exact record authority and safe context return; no evidence access inference |
| **Portia** | Safe support/timeline/response screen integration | Preserve protected student-support data, correction lifecycle and local record ownership |

**Producer source coverage still missing:** The Slice 1 collision inventory is **sampled**. Full nested `:notes` collision scanning, menu-specific shortcuts, path/data entry, exact confirmation and installed workflows remain explicit **consumer D3/D4 prerequisites**, not unnoticed completed work. Cross-repository adoption cannot be certified by Core's documentation PR.

## 5. Core #236 closure checklist and precise remaining gates

**Evidence prepared in this issue:**

- [x] Source-pinned baseline and ownership/collision **sample** in Slice 1 audit.
- [x] Explicit, planned public paths/signatures/types, capabilities and version policy in contract §§1–3.
- [x] Concrete planned handoff, caller return/revalidation, menu and result shapes, privacy and CLI parity in contract §4.
- [x] Synthetic Quillan/Notes and classroom-management success/stale/conflict traces in contract §§4.7–4.8.
- [x] Conformance vectors **H01–H11, C01–C13, R01–R12, P01–P12**, plus UX-01–UX-12 ownership mapping.
- [x] D-01–D-08 and Suite §§3,5–15 traceability, successor issue routing and source/install truthfulness.
- [x] No production feature, new Core record, migrated schema, module changes or falsely qualified public API introduced by documentation slices.

**Closure gates (architecture approved; PR CI and scope checks remain):**

- [x] **Owner approves the exact public contract and accepts ADR 0005.** The decision establishes architecture/D0 only, not runtime, installation, privacy, or consumer qualification.
- [ ] CI and the repository's normal full checks pass on the final PR branch/commit (including documentation/hygiene, Python tests, strict mypy and installed artifact checks as appropriate). A focused 55-test slice regression suite is **not** full project qualification.
- [ ] Reviewer verifies no unintended producer, Suite, release, CLI, private-data or production Core changes; resolve all remaining contract contradictions, if found.
- [ ] PR records exact reviewed final commit and states that Core #237–#244, Suite #51 and individual consumer acceptance are pending.

**Explicitly outside #236:** runtime H/C/R/P tests, complete nested-producer collision census, private-store threat-model test results, installed-wheel/consumer tests, real Windows/ARM64 color trials, qualified private backup, Suite teacher home and academic producer workflow improvements. Those gates cannot be marked passed based on this source-only audit.

**Owner-signoff PR evidence:** “Core #236 accepts the v1 technical teacher-experience interfaces and ADR 0005 as D0 architecture, with source-pinned gap audit, conformance vectors and owner/consumer handoff. Existing Core 0.6.6 runtime and published consumer releases remain unchanged. Focused menu tests passed in each slice; full PR CI must pass for the final owner-acceptance commit. No future capability is represented as importable, installed, release-qualified or adopted.”
