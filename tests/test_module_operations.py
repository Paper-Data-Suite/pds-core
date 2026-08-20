"""Tests for the neutral Core module-operations contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.module_operations import (
    MAX_MODULE_ATTENTION_SUMMARIES,
    MAX_MODULE_OPERATION_CODE_LENGTH,
    MAX_MODULE_OPERATION_COUNT,
    MODULE_OPERATIONS_CONTRACT_VERSION,
    MODULE_OPERATIONS_ENTRY_POINT_GROUP,
    ModuleAttentionReport,
    ModuleAttentionSummary,
    ModuleOperationsContractError,
    ModuleOperationsInvocationResult,
    ModuleOperationsNotice,
    ModuleOperationsProfile,
    ModuleOperationsRequest,
    ModuleOwnerActionRef,
    ModuleReadinessReport,
    invoke_module_attention,
    invoke_module_operations,
    invoke_module_readiness,
    validate_module_attention_report,
    validate_module_operations_invocation_result,
    validate_module_operations_profile,
    validate_module_operations_request,
    validate_module_owner_action_ref,
    validate_module_readiness_report,
)
from pds_core.routing_models import ModuleWorkRef


def _ready(_request: ModuleOperationsRequest) -> ModuleReadinessReport:
    return ModuleReadinessReport(evaluation="evaluated", ready=True)


def _attention(_request: ModuleOperationsRequest) -> ModuleAttentionReport:
    return ModuleAttentionReport(evaluation="evaluated")


def test_contract_identity_is_explicit() -> None:
    assert MODULE_OPERATIONS_CONTRACT_VERSION == "1"
    assert MODULE_OPERATIONS_ENTRY_POINT_GROUP == "paper_data_suite.module_operations"


def test_request_accepts_small_neutral_context_without_filesystem_access(
    tmp_path: Path,
) -> None:
    request = ModuleOperationsRequest(
        workspace_root=tmp_path.resolve(),
        active_school_year="2026-2027",
        class_id="english10_p2",
    )

    assert validate_module_operations_request(request) is request


def test_request_rejects_relative_workspace_invalid_school_year_and_class() -> None:
    with pytest.raises(ModuleOperationsContractError, match="absolute"):
        ModuleOperationsRequest(workspace_root=Path("relative"))
    with pytest.raises(ModuleOperationsContractError, match="school_year"):
        ModuleOperationsRequest(active_school_year="2026")
    with pytest.raises(ModuleOperationsContractError):
        ModuleOperationsRequest(class_id="../class")


def test_profile_supports_readiness_only_attention_only_or_both() -> None:
    readiness_only = ModuleOperationsProfile(
        module_id="scoreform",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=_ready,
    )
    attention_only = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        attention_provider=_attention,
    )
    both = ModuleOperationsProfile(
        module_id="concord",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=_ready,
        attention_provider=_attention,
    )

    assert validate_module_operations_profile(readiness_only) is readiness_only
    assert validate_module_operations_profile(attention_only) is attention_only
    assert validate_module_operations_profile(both) is both


def test_profile_rejects_no_capability_invalid_identity_and_noncallable() -> None:
    with pytest.raises(ModuleOperationsContractError, match="at least one"):
        ModuleOperationsProfile(
            module_id="concord",
            supported_core_operations_contract_versions=frozenset({"1"}),
        )
    with pytest.raises(ModuleOperationsContractError, match="lowercase"):
        ModuleOperationsProfile(
            module_id="Concord",
            supported_core_operations_contract_versions=frozenset({"1"}),
            readiness_provider=_ready,
        )
    with pytest.raises(ModuleOperationsContractError, match="callable"):
        ModuleOperationsProfile(
            module_id="concord",
            supported_core_operations_contract_versions=frozenset({"1"}),
            readiness_provider=object(),  # type: ignore[arg-type]
        )


def test_profile_contract_versions_are_frozen_and_must_be_nonempty() -> None:
    profile = ModuleOperationsProfile(
        module_id="concord",
        supported_core_operations_contract_versions={"1", "2"},  # type: ignore[arg-type]
        readiness_provider=_ready,
    )

    assert profile.supported_core_operations_contract_versions == frozenset(
        {"1", "2"}
    )

    with pytest.raises(ModuleOperationsContractError, match="must not be empty"):
        ModuleOperationsProfile(
            module_id="concord",
            supported_core_operations_contract_versions=frozenset(),
            readiness_provider=_ready,
        )


def test_unsupported_active_contract_remains_structurally_valid() -> None:
    profile = ModuleOperationsProfile(
        module_id="concord",
        supported_core_operations_contract_versions=frozenset({"2"}),
        readiness_provider=_ready,
    )

    assert validate_module_operations_profile(profile) is profile
    assert MODULE_OPERATIONS_CONTRACT_VERSION not in (
        profile.supported_core_operations_contract_versions
    )


def test_action_reference_is_inert_bounded_and_owner_validatable() -> None:
    action = ModuleOwnerActionRef(
        module_id="quillan",
        action_id="continue_review",
    )

    assert (
        validate_module_owner_action_ref(
            action,
            expected_module_id="quillan",
        )
        is action
    )
    with pytest.raises(ModuleOperationsContractError, match="owning module_id"):
        validate_module_owner_action_ref(
            action,
            expected_module_id="scoreform",
        )
    with pytest.raises(ModuleOperationsContractError, match="must not exceed"):
        ModuleOwnerActionRef(
            module_id="quillan",
            action_id="a" * (MAX_MODULE_OPERATION_CODE_LENGTH + 1),
        )
    with pytest.raises(ModuleOperationsContractError):
        ModuleOwnerActionRef(
            module_id="quillan",
            action_id="https://example.invalid/action",
        )


def test_notice_rejects_unbounded_or_multiline_text() -> None:
    with pytest.raises(ModuleOperationsContractError, match="line-separator"):
        ModuleOperationsNotice(code="workspace_missing", summary="first\nsecond")
    with pytest.raises(ModuleOperationsContractError, match="surrounding whitespace"):
        ModuleOperationsNotice(code="workspace_missing", summary=" padded ")


def test_readiness_distinguishes_unavailable_from_evaluated_false() -> None:
    unavailable = ModuleReadinessReport(
        evaluation="unavailable",
        ready=None,
        notices=(
            ModuleOperationsNotice(
                code="workspace_required",
                summary="A workspace is required to evaluate this capability.",
            ),
        ),
    )
    not_ready = ModuleReadinessReport(
        evaluation="evaluated",
        ready=False,
        notices=(
            ModuleOperationsNotice(
                code="local_state_invalid",
                summary="Required module-local state is invalid.",
            ),
        ),
    )

    assert unavailable.ready is None
    assert not_ready.ready is False
    assert validate_module_readiness_report(unavailable) is unavailable
    assert validate_module_readiness_report(not_ready) is not_ready


def test_readiness_enforces_evaluation_ready_invariant() -> None:
    with pytest.raises(ModuleOperationsContractError, match="boolean"):
        ModuleReadinessReport(evaluation="evaluated", ready=None)
    with pytest.raises(ModuleOperationsContractError, match="must be None"):
        ModuleReadinessReport(evaluation="unavailable", ready=False)


def test_readiness_report_validates_action_ownership() -> None:
    report = ModuleReadinessReport(
        evaluation="evaluated",
        ready=False,
        notices=(
            ModuleOperationsNotice(
                code="setup_required",
                summary="Module setup requires teacher attention.",
                action=ModuleOwnerActionRef(
                    module_id="quillan",
                    action_id="open_setup",
                ),
            ),
        ),
    )

    assert (
        validate_module_readiness_report(
            report,
            expected_module_id="quillan",
        )
        is report
    )
    with pytest.raises(ModuleOperationsContractError, match="owning module_id"):
        validate_module_readiness_report(
            report,
            expected_module_id="scoreform",
        )


def test_attention_distinguishes_empty_success_from_unavailable() -> None:
    empty = ModuleAttentionReport(evaluation="evaluated")
    unavailable = ModuleAttentionReport(
        evaluation="unavailable",
        notices=(
            ModuleOperationsNotice(
                code="workspace_required",
                summary="A workspace is required to evaluate attention.",
            ),
        ),
    )

    assert empty.evaluation == "evaluated"
    assert empty.summaries == ()
    assert unavailable.evaluation == "unavailable"


def test_unavailable_attention_cannot_contain_attention_summaries() -> None:
    summary = ModuleAttentionSummary(
        code="review_pending",
        label="Reviews need attention",
        count=2,
    )

    with pytest.raises(ModuleOperationsContractError, match="must be empty"):
        ModuleAttentionReport(
            evaluation="unavailable",
            summaries=(summary,),
        )


def test_attention_summary_supports_bounded_count_class_work_and_action() -> None:
    work_ref = ModuleWorkRef(
        module_id="scoreform",
        class_id="english10_p2",
        work_id="unit_1_quiz",
    )
    summary = ModuleAttentionSummary(
        code="scan_review",
        label="Returned papers need review",
        count=3,
        class_id="english10_p2",
        work_ref=work_ref,
        action=ModuleOwnerActionRef(
            module_id="scoreform",
            action_id="open_scan_review",
        ),
    )
    report = ModuleAttentionReport(
        evaluation="evaluated",
        summaries=(summary,),
    )

    assert (
        validate_module_attention_report(
            report,
            expected_module_id="scoreform",
        )
        is report
    )


def test_attention_summary_rejects_invalid_count_and_context_mismatch() -> None:
    with pytest.raises(ModuleOperationsContractError, match="integer"):
        ModuleAttentionSummary(
            code="review_pending",
            label="Reviews need attention",
            count=True,
        )
    with pytest.raises(ModuleOperationsContractError, match="between"):
        ModuleAttentionSummary(
            code="review_pending",
            label="Reviews need attention",
            count=MAX_MODULE_OPERATION_COUNT + 1,
        )
    with pytest.raises(ModuleOperationsContractError, match="class_id must match"):
        ModuleAttentionSummary(
            code="review_pending",
            label="Reviews need attention",
            class_id="english10_p2",
            work_ref=ModuleWorkRef(
                module_id="quillan",
                class_id="english10_p4",
                work_id="essay_1",
            ),
        )


def test_attention_report_validates_work_and_action_owner() -> None:
    foreign_work = ModuleAttentionReport(
        evaluation="evaluated",
        summaries=(
            ModuleAttentionSummary(
                code="review_pending",
                label="Reviews need attention",
                work_ref=ModuleWorkRef(
                    module_id="quillan",
                    class_id="english10_p2",
                    work_id="essay_1",
                ),
            ),
        ),
    )
    foreign_action = ModuleAttentionReport(
        evaluation="evaluated",
        summaries=(
            ModuleAttentionSummary(
                code="scan_review",
                label="Returned papers need review",
                action=ModuleOwnerActionRef(
                    module_id="quillan",
                    action_id="open_review",
                ),
            ),
        ),
    )

    with pytest.raises(ModuleOperationsContractError, match="work_ref.module_id"):
        validate_module_attention_report(
            foreign_work,
            expected_module_id="scoreform",
        )
    with pytest.raises(ModuleOperationsContractError, match="owning module_id"):
        validate_module_attention_report(
            foreign_action,
            expected_module_id="scoreform",
        )


def test_attention_summary_collection_is_bounded() -> None:
    summary = ModuleAttentionSummary(
        code="review_pending",
        label="Reviews need attention",
    )

    with pytest.raises(ModuleOperationsContractError, match="result bound"):
        ModuleAttentionReport(
            evaluation="evaluated",
            summaries=(summary,) * (MAX_MODULE_ATTENTION_SUMMARIES + 1),
        )


def test_report_collections_are_immutable_tuples() -> None:
    notice = ModuleOperationsNotice(
        code="workspace_required",
        summary="A workspace is required.",
    )
    summary = ModuleAttentionSummary(
        code="review_pending",
        label="Reviews need attention",
    )

    readiness = ModuleReadinessReport(
        evaluation="unavailable",
        ready=None,
        notices=[notice],  # type: ignore[arg-type]
    )
    attention = ModuleAttentionReport(
        evaluation="evaluated",
        summaries=[summary],  # type: ignore[arg-type]
        notices=[notice],  # type: ignore[arg-type]
    )

    assert readiness.notices == (notice,)
    assert attention.summaries == (summary,)
    assert attention.notices == (notice,)


def test_readiness_invocation_distinguishes_absent_unavailable_and_not_ready() -> None:
    attention_only = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        attention_provider=_attention,
    )
    absent = invoke_module_readiness(attention_only, ModuleOperationsRequest())

    def unavailable_provider(
        _request: ModuleOperationsRequest,
    ) -> ModuleReadinessReport:
        return ModuleReadinessReport(evaluation="unavailable", ready=None)

    unavailable_profile = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=unavailable_provider,
    )
    unavailable = invoke_module_readiness(
        unavailable_profile,
        ModuleOperationsRequest(),
    )

    def not_ready_provider(
        _request: ModuleOperationsRequest,
    ) -> ModuleReadinessReport:
        return ModuleReadinessReport(evaluation="evaluated", ready=False)

    not_ready_profile = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=not_ready_provider,
    )
    not_ready = invoke_module_readiness(
        not_ready_profile,
        ModuleOperationsRequest(),
    )

    assert absent.code == "module_operations.capability_absent"
    assert not absent.provider_call_attempted
    assert absent.report is None

    assert unavailable.code == "module_operations.evaluation_unavailable"
    assert unavailable.provider_call_succeeded
    assert unavailable.result_validation == "passed"
    assert isinstance(unavailable.report, ModuleReadinessReport)
    assert unavailable.report.ready is None

    assert not_ready.code == "module_operations.evaluated"
    assert isinstance(not_ready.report, ModuleReadinessReport)
    assert not_ready.report.ready is False


def test_attention_invocation_preserves_successful_empty_result() -> None:
    profile = ModuleOperationsProfile(
        module_id="scoreform",
        supported_core_operations_contract_versions=frozenset({"1"}),
        attention_provider=_attention,
    )

    result = invoke_module_attention(profile, ModuleOperationsRequest())

    assert result.code == "module_operations.evaluated"
    assert result.provider_call_attempted
    assert result.provider_call_succeeded
    assert result.result_validation == "passed"
    assert isinstance(result.report, ModuleAttentionReport)
    assert result.report.summaries == ()


def test_capability_exception_is_bounded_and_does_not_leak_provider_text() -> None:
    def raises(_request: ModuleOperationsRequest) -> ModuleReadinessReport:
        raise RuntimeError("student-name C:/private/workspace secret")

    profile = ModuleOperationsProfile(
        module_id="concord",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=raises,
    )

    result = invoke_module_readiness(profile, ModuleOperationsRequest())

    assert result.code == "module_operations.provider_failed"
    assert result.provider_call_attempted
    assert not result.provider_call_succeeded
    assert result.result_validation == "not_attempted"
    assert result.report is None
    assert "student-name" not in result.message
    assert "C:/private" not in result.message


def test_capability_invalid_result_is_distinct_from_provider_failure() -> None:
    def invalid(_request: ModuleOperationsRequest) -> object:
        return object()

    profile = ModuleOperationsProfile(
        module_id="concord",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=invalid,  # type: ignore[arg-type]
    )

    result = invoke_module_readiness(profile, ModuleOperationsRequest())

    assert result.code == "module_operations.result_invalid"
    assert result.provider_call_attempted
    assert result.provider_call_succeeded
    assert result.result_validation == "failed"
    assert result.report is None


def test_invocation_revalidates_module_owned_action_references() -> None:
    def foreign_action(
        _request: ModuleOperationsRequest,
    ) -> ModuleReadinessReport:
        return ModuleReadinessReport(
            evaluation="evaluated",
            ready=False,
            notices=(
                ModuleOperationsNotice(
                    code="setup_required",
                    summary="Module setup requires attention.",
                    action=ModuleOwnerActionRef(
                        module_id="quillan",
                        action_id="open_setup",
                    ),
                ),
            ),
        )

    profile = ModuleOperationsProfile(
        module_id="scoreform",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=foreign_action,
    )

    result = invoke_module_readiness(profile, ModuleOperationsRequest())

    assert result.code == "module_operations.result_invalid"
    assert result.result_validation == "failed"


def test_attention_invocation_rejects_wrong_requested_class_context() -> None:
    def wrong_class(
        _request: ModuleOperationsRequest,
    ) -> ModuleAttentionReport:
        return ModuleAttentionReport(
            evaluation="evaluated",
            summaries=(
                ModuleAttentionSummary(
                    code="review_pending",
                    label="Reviews need attention",
                    class_id="english10_p4",
                    work_ref=ModuleWorkRef(
                        module_id="quillan",
                        class_id="english10_p4",
                        work_id="essay_1",
                    ),
                ),
            ),
        )

    profile = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        attention_provider=wrong_class,
    )

    result = invoke_module_attention(
        profile,
        ModuleOperationsRequest(class_id="english10_p2"),
    )

    assert result.code == "module_operations.result_invalid"
    assert result.result_validation == "failed"


def test_combined_invocation_isolates_readiness_failure_from_attention() -> None:
    calls = {"readiness": 0, "attention": 0}

    def readiness(_request: ModuleOperationsRequest) -> ModuleReadinessReport:
        calls["readiness"] += 1
        raise RuntimeError("readiness failure")

    def attention(_request: ModuleOperationsRequest) -> ModuleAttentionReport:
        calls["attention"] += 1
        return ModuleAttentionReport(
            evaluation="evaluated",
            summaries=(
                ModuleAttentionSummary(
                    code="review_pending",
                    label="Reviews need attention",
                    count=2,
                ),
            ),
        )

    profile = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        readiness_provider=readiness,
        attention_provider=attention,
    )

    readiness_result, attention_result = invoke_module_operations(
        profile,
        ModuleOperationsRequest(),
    )

    assert readiness_result.capability == "readiness"
    assert readiness_result.code == "module_operations.provider_failed"
    assert attention_result.capability == "attention"
    assert attention_result.code == "module_operations.evaluated"
    assert calls == {"readiness": 1, "attention": 1}


def test_unsupported_operations_contract_is_not_invoked() -> None:
    calls = {"readiness": 0}

    def readiness(_request: ModuleOperationsRequest) -> ModuleReadinessReport:
        calls["readiness"] += 1
        return ModuleReadinessReport(evaluation="evaluated", ready=True)

    profile = ModuleOperationsProfile(
        module_id="concord",
        supported_core_operations_contract_versions=frozenset({"2"}),
        readiness_provider=readiness,
    )

    with pytest.raises(ModuleOperationsContractError, match="active Core"):
        invoke_module_readiness(profile, ModuleOperationsRequest())

    assert calls["readiness"] == 0


def test_invocation_result_model_rejects_inconsistent_state() -> None:
    with pytest.raises(ModuleOperationsContractError, match="inconsistent"):
        ModuleOperationsInvocationResult(
            module_id="scoreform",
            capability="attention",
            code="module_operations.capability_absent",
            message="Module does not expose this operations capability.",
            provider_call_attempted=True,
            provider_call_succeeded=False,
            result_validation="not_attempted",
        )

    valid = invoke_module_attention(
        ModuleOperationsProfile(
            module_id="scoreform",
            supported_core_operations_contract_versions=frozenset({"1"}),
            attention_provider=_attention,
        ),
        ModuleOperationsRequest(),
    )
    assert validate_module_operations_invocation_result(valid) is valid



def test_attention_failure_is_not_misreported_as_empty_attention() -> None:
    def raises(_request: ModuleOperationsRequest) -> ModuleAttentionReport:
        raise RuntimeError("private attention failure")

    profile = ModuleOperationsProfile(
        module_id="quillan",
        supported_core_operations_contract_versions=frozenset({"1"}),
        attention_provider=raises,
    )

    failed = invoke_module_attention(profile, ModuleOperationsRequest())
    empty = invoke_module_attention(
        ModuleOperationsProfile(
            module_id="scoreform",
            supported_core_operations_contract_versions=frozenset({"1"}),
            attention_provider=_attention,
        ),
        ModuleOperationsRequest(),
    )

    assert failed.code == "module_operations.provider_failed"
    assert failed.report is None
    assert empty.code == "module_operations.evaluated"
    assert isinstance(empty.report, ModuleAttentionReport)
    assert empty.report.summaries == ()
