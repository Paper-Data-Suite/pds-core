"""Durable checks for the active v0.6 release documentation."""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path

from pds_core.academic_period_queries import (
    list_academic_periods_containing_date,
    list_child_academic_periods,
)
from pds_core.academic_period_storage import (
    load_current_academic_period_calendar,
    resolve_academic_period_ref,
    write_academic_period_calendar,
)
from pds_core.academic_periods import (
    ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
    ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
    AcademicPeriod,
    AcademicPeriodCalendar,
    AcademicPeriodRef,
)
from pds_core.publication_compatibility import (
    PublicationContractSupport,
    PublicationProducerProfile,
    SourceRecordContractSupport,
)
from pds_core.registry_services import (
    AcademicWorkRegistrationRequest,
    register_academic_work,
    update_academic_work_registration,
)
from pds_core.routes import module_work_dir
from pds_core.routing_models import ModuleRecordRef, ModuleWorkRef


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_DOCUMENTS = (
    PROJECT_ROOT / "docs" / "academic_registry_integration.md",
    PROJECT_ROOT / "docs" / "academic_registry_recovery.md",
    PROJECT_ROOT / "docs" / "releases" / "v0.6.0.md",
    PROJECT_ROOT / "docs" / "releases" / "v0.6.1.md",
)
MARKDOWN_LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def active_markdown_files() -> tuple[Path, ...]:
    files = [PROJECT_ROOT / "README.md", PROJECT_ROOT / "SECURITY.md"]
    files.extend(
        path
        for path in (PROJECT_ROOT / "docs").rglob("*.md")
        if path != PROJECT_ROOT / "docs" / "releases" / "v0.5.0.md"
    )
    return tuple(sorted(files))


def test_required_v061_documents_exist() -> None:
    assert all(path.is_file() for path in REQUIRED_DOCUMENTS)


def test_active_release_and_dependency_guidance_is_v061() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    security = (PROJECT_ROOT / "SECURITY.md").read_text(encoding="utf-8")
    active_text = "\n".join(
        path.read_text(encoding="utf-8") for path in active_markdown_files()
    )

    grouping_contract = (
        PROJECT_ROOT / "docs" / "grouping_signal_set_v1.md"
    ).read_text(encoding="utf-8")
    assert "Version 0.6.1" in readme
    assert "pds-core>=0.6,<0.7" in readme
    assert "pds-core>=0.6.1,<0.7" in readme
    assert re.search(r"\|\s*0\.6\.x\s*\|\s*Yes\s*\|", security)
    assert ">=0.5,<0.6" not in active_text
    assert "unreleased v0.6.1 work" not in readme
    assert "standalone/release qualification remains #184" not in grouping_contract


def test_routing_and_publication_entry_points_are_distinct() -> None:
    guide = REQUIRED_DOCUMENTS[0].read_text(encoding="utf-8")

    assert "paper_data_suite.modules" in guide
    assert "paper_data_suite.publication_producers" in guide
    assert "A routing profile does not make a module a publication producer." in guide
    assert "A publication profile does not make a module routable." in guide


def test_relative_markdown_links_resolve() -> None:
    broken: list[str] = []
    for document in active_markdown_files():
        text = document.read_text(encoding="utf-8")
        for raw_target in MARKDOWN_LINK.findall(text):
            target = raw_target.strip().split(maxsplit=1)[0].strip("<>")
            if not target or target.startswith(("#", "http://", "https://", "mailto:")):
                continue
            relative = target.split("#", maxsplit=1)[0]
            if relative and not (document.parent / relative).resolve().exists():
                broken.append(f"{document.relative_to(PROJECT_ROOT)} -> {target}")
    assert broken == []


def test_documented_academic_period_workflow(tmp_path: Path) -> None:
    now = datetime(2026, 8, 3, 12, tzinfo=UTC)
    first = AcademicPeriodCalendar(
        ACADEMIC_PERIOD_CALENDAR_SCHEMA_VERSION,
        ACADEMIC_PERIOD_CALENDAR_RECORD_TYPE,
        "2026-2027",
        1,
        now,
        now,
        (
            AcademicPeriod(
                "semester_1", "semester", "Semester 1",
                date(2026, 8, 20), date(2026, 12, 20), None, 1, "planned",
            ),
            AcademicPeriod(
                "quarter_1", "quarter", "Quarter 1",
                date(2026, 8, 20), date(2026, 10, 20), "semester_1", 1, "planned",
            ),
        ),
    )
    write_academic_period_calendar(tmp_path, first, expected_current_revision=None)
    second = replace(
        first,
        calendar_revision=2,
        updated_at=datetime(2026, 8, 20, 12, tzinfo=UTC),
        periods=tuple(replace(item, lifecycle="active") for item in first.periods),
    )
    write_academic_period_calendar(tmp_path, second, expected_current_revision=1)

    current = load_current_academic_period_calendar(tmp_path, "2026-2027")
    assert current is not None and current.calendar_revision == 2
    assert [
        item.period_id
        for item in list_child_academic_periods(current, "semester_1")
    ] == ["quarter_1"]
    assert len(
        list_academic_periods_containing_date(current, date(2026, 9, 1))
    ) == 2
    assert resolve_academic_period_ref(
        tmp_path, AcademicPeriodRef("2026-2027", "quarter_1")
    ).label == "Quarter 1"


def test_documented_registration_and_profile_examples(tmp_path: Path) -> None:
    work = ModuleWorkRef("quillan", "english12_p4", "personal_narrative")
    module_work_dir(tmp_path, work).mkdir(parents=True)
    request = AcademicWorkRegistrationRequest(
        work=work,
        producer_contract_version="assignment_v2",
        title="Personal Narrative",
        work_kind="assignment",
        academic_intent="summative",
        lifecycle="active",
        source_records=(
            ModuleRecordRef("quillan", "assignment", "personal_narrative", "2"),
        ),
    )
    assert register_academic_work(tmp_path, request).disposition == "created"
    assert register_academic_work(tmp_path, request).disposition == "existing"
    update = replace(request, title="Personal Narrative Final", lifecycle="closed")
    updated = update_academic_work_registration(
        tmp_path, update, expected_current_revision=1
    )
    assert updated.disposition == "updated"
    assert updated.registration.registration_revision == 2

    academic = PublicationProducerProfile(
        "synthetic_academic", "Synthetic Academic Producer",
        frozenset({"1"}), frozenset({"assignment_v1"}),
        (PublicationContractSupport(
            "academic_result_set", frozenset({"results_manifest_v1"}),
            frozenset({"points", "multiple_attempts"}),
            (SourceRecordContractSupport("result_set", frozenset({"1"})),),
            False,
        ),),
    )
    intervention = PublicationProducerProfile(
        "synthetic_intervention", "Synthetic Intervention Producer",
        frozenset({"1"}), frozenset(),
        (PublicationContractSupport(
            "intervention_record_set", frozenset({"intervention_manifest_v1"}),
            frozenset({"intervention_history", "intervention_status"}),
        ),),
    )
    assert academic.supported_academic_work_contract_versions == frozenset(
        {"assignment_v1"}
    )
    assert intervention.supported_academic_work_contract_versions == frozenset()


def test_module_operations_contract_documentation_is_explicit() -> None:
    operations_path = PROJECT_ROOT / "docs" / "module_operations.md"
    diagnostics_path = PROJECT_ROOT / "docs" / "provider_diagnostics.md"
    assert operations_path.is_file()
    assert diagnostics_path.is_file()

    operations = operations_path.read_text(encoding="utf-8")
    diagnostics = diagnostics_path.read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    for marker in (
        "paper_data_suite.module_operations",
        'MODULE_OPERATIONS_CONTRACT_VERSION = "1"',
        "successful empty attention",
        "module_operations.capability_absent",
        "module_operations.evaluation_unavailable",
        "module_operations.evaluated",
        "module_operations.provider_failed",
        "module_operations.result_invalid",
        "operations provider present",
        "Grouping-signal separation",
    ):
        assert marker in operations

    assert "module_operations" in diagnostics
    assert "ModuleOperationsProfile" in diagnostics
    assert "does not invoke its readiness or" in diagnostics
    assert "module_operations.provider_failed" in diagnostics
    assert "docs/module_operations.md" in readme
