# AP Computer Science Principles and NJSLS Computer Science Alignment

## Status and scope

This is a **Paper Data Suite-curated** instructional crosswalk. It is **not an official College Board or NJDOE crosswalk**, is not endorsed by either organization, and **does not assert equivalence** between AP Computer Science Principles framework elements and New Jersey Student Learning Standards. It exists to help teachers select defensible references from both frameworks while planning or assessing instruction.

The AP side uses only the minimal structural reference IDs bundled by `ap_csp_fall_2023`; authoritative AP wording remains in the College Board Fall 2023 Course and Exam Description. The NJSLS side uses the durable IDs from Core's `njsls_csdt_2020` pack.

## Broad instructional crosswalk

| AP CSP reference | Related NJSLS Computer Science references | PDS-curated rationale |
| --- | --- | --- |
| `ap-csp-2023:big-idea:crd` | `njsls-csdt:8.1.12.AP.4`, `njsls-csdt:8.1.12.AP.7`, `njsls-csdt:8.1.12.AP.8`, `njsls-csdt:8.1.12.AP.9` | Both frameworks address iterative development, collaboration, user feedback, usability/accessibility, and communication of design decisions. The relationship is instructional overlap, not equivalence. |
| `ap-csp-2023:big-idea:dat` | `njsls-csdt:8.1.12.DA.1`, `njsls-csdt:8.1.12.DA.2`, `njsls-csdt:8.1.12.DA.5`, `njsls-csdt:8.1.12.DA.6` | These NJSLS expectations provide a high-school data-analysis cluster relevant to AP CSP's Data content, including representation, organization, visualization, and computational models. |
| `ap-csp-2023:big-idea:aap` | `njsls-csdt:8.1.12.AP.1`, `njsls-csdt:8.1.12.AP.2`, `njsls-csdt:8.1.12.AP.3`, `njsls-csdt:8.1.12.AP.4`, `njsls-csdt:8.1.12.AP.5`, `njsls-csdt:8.1.12.AP.6` | The NJSLS Algorithms & Programming expectations supply the closest state-standard cluster for algorithm design, generalized solutions, control structures, iterative development, decomposition, procedures, and program artifacts. |
| `ap-csp-2023:big-idea:csn` | `njsls-csdt:8.1.12.CS.1`, `njsls-csdt:8.1.12.CS.2`, `njsls-csdt:8.1.12.CS.3`, `njsls-csdt:8.1.12.NI.1`, `njsls-csdt:8.1.12.NI.2`, `njsls-csdt:8.1.12.NI.3`, `njsls-csdt:8.1.12.NI.4` | These expectations cover computing-system abstraction and interaction plus network architecture, reliability, security, threats, and protection of data. |
| `ap-csp-2023:big-idea:ioc` | `njsls-csdt:8.1.12.IC.1`, `njsls-csdt:8.1.12.IC.2`, `njsls-csdt:8.1.12.IC.3` | The NJSLS Impacts of Computing cluster addresses personal, ethical, social, economic, cultural, equity, and emerging-technology effects relevant to AP CSP's Impact of Computing content. |

This table intentionally stays at a broad, defensible level. It does not automatically map every AP Learning Objective to a New Jersey Performance Expectation. A future provenance-aware mapping contract can support finer-grained crosswalks once requirements across AP, NJSLS, CSTA, and other frameworks are considered together.

## Mixed-framework local profile workflow

Core profiles may reference standards from more than one installed source. After installing both `ap_csp_fall_2023` and `njsls_csdt_2020`, a teacher may create a local profile containing selected AP reference IDs and selected NJSLS IDs. For example, a technically valid local profile could include:

```text
ap-csp-2023:lo:AAP-2.A
njsls-csdt:8.1.12.AP.1
```

The profile expresses the teacher's local instructional selection. Its existence does not convert that pair into an official mapping, prove equivalence, or alter either source framework. Quillan and ScoreForm consume the selected durable IDs through the same Core profile-selection APIs used for single-framework profiles.

## Copyright and trademark boundary

The AP starter pack contains identifiers, short structural titles, and Core-authored reference metadata only. It does not reproduce College Board Learning Objective text, Essential Knowledge, practice-skill descriptions, assessment content, AP Classroom material, performance-task directions, scoring guidance, or logos. Consult the official College Board CED for authoritative AP CSP content. `AP`, `Advanced Placement`, and related marks belong to College Board; Paper Data Suite is not affiliated with or endorsed by College Board.
