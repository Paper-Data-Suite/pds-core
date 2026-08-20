"""Neutral module-operations provider contracts for readiness and attention."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol, TypeAlias, cast

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.routing_models import ModuleWorkRef, validate_module_work_ref
from pds_core.school_years import SchoolYearValidationError, validate_school_year

MODULE_OPERATIONS_CONTRACT_VERSION: Final[str] = "1"
MODULE_OPERATIONS_ENTRY_POINT_GROUP: Final[str] = "paper_data_suite.module_operations"

MAX_MODULE_OPERATIONS_NOTICES: Final[int] = 16
MAX_MODULE_ATTENTION_SUMMARIES: Final[int] = 32
MAX_MODULE_OPERATION_CODE_LENGTH: Final[int] = 64
MAX_MODULE_OPERATION_LABEL_LENGTH: Final[int] = 160
MAX_MODULE_OPERATION_SUMMARY_LENGTH: Final[int] = 240
MAX_MODULE_OPERATION_COUNT: Final[int] = 1_000_000

ModuleCapabilityEvaluation: TypeAlias = Literal["evaluated", "unavailable"]
ModuleOperationsCapability: TypeAlias = Literal["readiness", "attention"]
ModuleOperationsInvocationCode: TypeAlias = Literal[
    "module_operations.capability_absent",
    "module_operations.evaluation_unavailable",
    "module_operations.evaluated",
    "module_operations.provider_failed",
    "module_operations.result_invalid",
]
ModuleOperationsValidationOutcome: TypeAlias = Literal[
    "not_attempted",
    "passed",
    "failed",
]


class ModuleOperationsContractError(ValueError):
    """Raised when a shared module-operations value is structurally invalid."""


@dataclass(frozen=True, slots=True)
class ModuleOperationsRequest:
    """Small neutral context supplied to one module operations capability."""

    workspace_root: Path | None = None
    active_school_year: str | None = None
    class_id: str | None = None

    def __post_init__(self) -> None:
        if self.active_school_year is not None:
            object.__setattr__(
                self,
                "active_school_year",
                _validated_school_year(self.active_school_year),
            )
        _validate_request_fields(self)


@dataclass(frozen=True, slots=True)
class ModuleOwnerActionRef:
    """Opaque reference that routes a future action back to its owning module."""

    module_id: str
    action_id: str

    def __post_init__(self) -> None:
        _validate_lowercase_identifier(self.module_id, "module_id")
        _validate_bounded_identifier(self.action_id, "action_id")


@dataclass(frozen=True, slots=True)
class ModuleOperationsNotice:
    """Bounded module-owned explanatory notice for an operations report."""

    code: str
    summary: str
    action: ModuleOwnerActionRef | None = None

    def __post_init__(self) -> None:
        _validate_bounded_identifier(self.code, "code")
        _validate_safe_text(
            self.summary,
            "summary",
            max_length=MAX_MODULE_OPERATION_SUMMARY_LENGTH,
        )
        if self.action is not None:
            _require_action_ref(self.action)


@dataclass(frozen=True, slots=True)
class ModuleAttentionSummary:
    """One privacy-minimal module-owned teacher-attention summary."""

    code: str
    label: str
    count: int | None = None
    class_id: str | None = None
    work_ref: ModuleWorkRef | None = None
    action: ModuleOwnerActionRef | None = None

    def __post_init__(self) -> None:
        _validate_attention_summary_fields(self)


@dataclass(frozen=True, slots=True)
class ModuleReadinessReport:
    """Bounded readiness evaluation returned by one module capability."""

    evaluation: ModuleCapabilityEvaluation
    ready: bool | None
    notices: tuple[ModuleOperationsNotice, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "notices", tuple(self.notices))
        _validate_readiness_report_fields(self)


@dataclass(frozen=True, slots=True)
class ModuleAttentionReport:
    """Bounded teacher-attention evaluation returned by one module capability."""

    evaluation: ModuleCapabilityEvaluation
    summaries: tuple[ModuleAttentionSummary, ...] = ()
    notices: tuple[ModuleOperationsNotice, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "summaries", tuple(self.summaries))
        object.__setattr__(self, "notices", tuple(self.notices))
        _validate_attention_report_fields(self)


class ModuleReadinessProvider(Protocol):
    """Evaluate module-owned operational readiness for one neutral request."""

    def __call__(
        self,
        request: ModuleOperationsRequest,
        /,
    ) -> ModuleReadinessReport: ...


class ModuleAttentionProvider(Protocol):
    """Evaluate module-owned teacher attention for one neutral request."""

    def __call__(
        self,
        request: ModuleOperationsRequest,
        /,
    ) -> ModuleAttentionReport: ...


@dataclass(frozen=True, slots=True)
class ModuleOperationsProfile:
    """One installed module's shared operations capabilities."""

    module_id: str
    supported_core_operations_contract_versions: frozenset[str]
    readiness_provider: ModuleReadinessProvider | None = None
    attention_provider: ModuleAttentionProvider | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "supported_core_operations_contract_versions",
            _freeze_contract_versions(
                self.supported_core_operations_contract_versions
            ),
        )
        _validate_profile_fields(self)


ModuleOperationsReport: TypeAlias = ModuleReadinessReport | ModuleAttentionReport


@dataclass(frozen=True, slots=True)
class ModuleOperationsInvocationResult:
    """Bounded outcome for one module-owned operations capability invocation."""

    module_id: str
    capability: ModuleOperationsCapability
    code: ModuleOperationsInvocationCode
    message: str
    provider_call_attempted: bool
    provider_call_succeeded: bool
    result_validation: ModuleOperationsValidationOutcome
    report: ModuleOperationsReport | None = None

    def __post_init__(self) -> None:
        _validate_invocation_result_fields(self)


def validate_module_operations_request(
    request: ModuleOperationsRequest,
) -> ModuleOperationsRequest:
    """Revalidate and return a module-operations request."""
    if not isinstance(request, ModuleOperationsRequest):
        raise ModuleOperationsContractError(
            "request must be a ModuleOperationsRequest."
        )
    _validate_request_fields(request)
    return request


def validate_module_owner_action_ref(
    action: ModuleOwnerActionRef,
    *,
    expected_module_id: str | None = None,
) -> ModuleOwnerActionRef:
    """Revalidate an opaque owner-routed action reference."""
    if not isinstance(action, ModuleOwnerActionRef):
        raise ModuleOperationsContractError(
            "action must be a ModuleOwnerActionRef."
        )
    _validate_lowercase_identifier(action.module_id, "module_id")
    _validate_bounded_identifier(action.action_id, "action_id")
    if expected_module_id is not None:
        _validate_lowercase_identifier(expected_module_id, "expected_module_id")
        if action.module_id != expected_module_id:
            raise ModuleOperationsContractError(
                "action.module_id must match the owning module_id."
            )
    return action


def validate_module_readiness_report(
    report: ModuleReadinessReport,
    *,
    expected_module_id: str | None = None,
) -> ModuleReadinessReport:
    """Revalidate a bounded module readiness report."""
    if not isinstance(report, ModuleReadinessReport):
        raise ModuleOperationsContractError(
            "report must be a ModuleReadinessReport."
        )
    _validate_readiness_report_fields(report)
    _validate_report_owner(report.notices, (), expected_module_id)
    return report


def validate_module_attention_report(
    report: ModuleAttentionReport,
    *,
    expected_module_id: str | None = None,
) -> ModuleAttentionReport:
    """Revalidate a bounded module attention report."""
    if not isinstance(report, ModuleAttentionReport):
        raise ModuleOperationsContractError(
            "report must be a ModuleAttentionReport."
        )
    _validate_attention_report_fields(report)
    _validate_report_owner(report.notices, report.summaries, expected_module_id)
    return report


def validate_module_operations_profile(
    profile: ModuleOperationsProfile,
) -> ModuleOperationsProfile:
    """Revalidate and return a module-operations profile."""
    if not isinstance(profile, ModuleOperationsProfile):
        raise ModuleOperationsContractError(
            "profile must be a ModuleOperationsProfile."
        )
    _validate_profile_fields(profile)
    return profile


def validate_module_operations_invocation_result(
    result: ModuleOperationsInvocationResult,
) -> ModuleOperationsInvocationResult:
    """Revalidate and return a bounded capability invocation result."""
    if not isinstance(result, ModuleOperationsInvocationResult):
        raise ModuleOperationsContractError(
            "result must be a ModuleOperationsInvocationResult."
        )
    _validate_invocation_result_fields(result)
    return result


def invoke_module_readiness(
    profile: ModuleOperationsProfile,
    request: ModuleOperationsRequest,
) -> ModuleOperationsInvocationResult:
    """Invoke one module readiness capability with bounded failure isolation."""
    validated_profile = _validate_invocation_inputs(profile, request)
    return _invoke_capability(validated_profile, request, "readiness")


def invoke_module_attention(
    profile: ModuleOperationsProfile,
    request: ModuleOperationsRequest,
) -> ModuleOperationsInvocationResult:
    """Invoke one module attention capability with bounded failure isolation."""
    validated_profile = _validate_invocation_inputs(profile, request)
    return _invoke_capability(validated_profile, request, "attention")


def invoke_module_operations(
    profile: ModuleOperationsProfile,
    request: ModuleOperationsRequest,
) -> tuple[ModuleOperationsInvocationResult, ModuleOperationsInvocationResult]:
    """Invoke readiness and attention independently in deterministic order."""
    validated_profile = _validate_invocation_inputs(profile, request)
    return (
        _invoke_capability(validated_profile, request, "readiness"),
        _invoke_capability(validated_profile, request, "attention"),
    )


def _validate_invocation_inputs(
    profile: ModuleOperationsProfile,
    request: ModuleOperationsRequest,
) -> ModuleOperationsProfile:
    validated_profile = validate_module_operations_profile(profile)
    validate_module_operations_request(request)
    if (
        MODULE_OPERATIONS_CONTRACT_VERSION
        not in validated_profile.supported_core_operations_contract_versions
    ):
        raise ModuleOperationsContractError(
            "profile does not support the active Core module-operations contract."
        )
    return validated_profile


def _invoke_capability(
    profile: ModuleOperationsProfile,
    request: ModuleOperationsRequest,
    capability: ModuleOperationsCapability,
) -> ModuleOperationsInvocationResult:
    provider: ModuleReadinessProvider | ModuleAttentionProvider | None
    if capability == "readiness":
        provider = profile.readiness_provider
    else:
        provider = profile.attention_provider

    if provider is None:
        return _invocation_result(
            module_id=profile.module_id,
            capability=capability,
            code="module_operations.capability_absent",
            message="Module does not expose this operations capability.",
        )

    try:
        raw_report = provider(request)
    except Exception:
        return _invocation_result(
            module_id=profile.module_id,
            capability=capability,
            code="module_operations.provider_failed",
            message="Module operations capability raised during evaluation.",
            provider_call_attempted=True,
        )

    try:
        report = _validate_invoked_report(
            raw_report,
            capability=capability,
            expected_module_id=profile.module_id,
            request=request,
        )
    except Exception:
        return _invocation_result(
            module_id=profile.module_id,
            capability=capability,
            code="module_operations.result_invalid",
            message="Module operations capability returned an invalid report.",
            provider_call_attempted=True,
            provider_call_succeeded=True,
            result_validation="failed",
        )

    code: ModuleOperationsInvocationCode
    message: str
    if report.evaluation == "unavailable":
        code = "module_operations.evaluation_unavailable"
        message = (
            "Module could not evaluate this capability for the supplied context."
        )
    else:
        code = "module_operations.evaluated"
        message = "Module operations capability evaluated successfully."

    return _invocation_result(
        module_id=profile.module_id,
        capability=capability,
        code=code,
        message=message,
        provider_call_attempted=True,
        provider_call_succeeded=True,
        result_validation="passed",
        report=report,
    )


def _validate_invoked_report(
    value: object,
    *,
    capability: ModuleOperationsCapability,
    expected_module_id: str,
    request: ModuleOperationsRequest,
) -> ModuleOperationsReport:
    if capability == "readiness":
        if not isinstance(value, ModuleReadinessReport):
            raise ModuleOperationsContractError(
                "readiness capability must return ModuleReadinessReport."
            )
        return validate_module_readiness_report(
            value,
            expected_module_id=expected_module_id,
        )

    if not isinstance(value, ModuleAttentionReport):
        raise ModuleOperationsContractError(
            "attention capability must return ModuleAttentionReport."
        )
    validated = validate_module_attention_report(
        value,
        expected_module_id=expected_module_id,
    )
    _validate_attention_request_context(validated, request)
    return validated


def _validate_attention_request_context(
    report: ModuleAttentionReport,
    request: ModuleOperationsRequest,
) -> None:
    if request.class_id is None:
        return
    for summary in report.summaries:
        if summary.class_id is not None and summary.class_id != request.class_id:
            raise ModuleOperationsContractError(
                "attention summary class_id must match the requested class_id."
            )
        if (
            summary.work_ref is not None
            and summary.work_ref.class_id != request.class_id
        ):
            raise ModuleOperationsContractError(
                "attention summary work_ref.class_id must match the requested "
                "class_id."
            )


def _invocation_result(
    *,
    module_id: str,
    capability: ModuleOperationsCapability,
    code: ModuleOperationsInvocationCode,
    message: str,
    provider_call_attempted: bool = False,
    provider_call_succeeded: bool = False,
    result_validation: ModuleOperationsValidationOutcome = "not_attempted",
    report: ModuleOperationsReport | None = None,
) -> ModuleOperationsInvocationResult:
    return ModuleOperationsInvocationResult(
        module_id=module_id,
        capability=capability,
        code=code,
        message=message,
        provider_call_attempted=provider_call_attempted,
        provider_call_succeeded=provider_call_succeeded,
        result_validation=result_validation,
        report=report,
    )


def _validate_invocation_result_fields(
    result: ModuleOperationsInvocationResult,
) -> None:
    _validate_lowercase_identifier(result.module_id, "module_id")
    if result.capability not in {"readiness", "attention"}:
        raise ModuleOperationsContractError(
            "capability must be 'readiness' or 'attention'."
        )
    valid_codes = {
        "module_operations.capability_absent",
        "module_operations.evaluation_unavailable",
        "module_operations.evaluated",
        "module_operations.provider_failed",
        "module_operations.result_invalid",
    }
    if result.code not in valid_codes:
        raise ModuleOperationsContractError("invalid module-operations result code.")
    _validate_safe_text(
        result.message,
        "message",
        max_length=MAX_MODULE_OPERATION_SUMMARY_LENGTH,
    )
    if result.result_validation not in {"not_attempted", "passed", "failed"}:
        raise ModuleOperationsContractError(
            "result_validation must be not_attempted, passed, or failed."
        )

    if result.code == "module_operations.capability_absent":
        if (
            result.provider_call_attempted
            or result.provider_call_succeeded
            or result.result_validation != "not_attempted"
            or result.report is not None
        ):
            raise ModuleOperationsContractError(
                "capability-absent result contains inconsistent invocation state."
            )
        return

    if result.code == "module_operations.provider_failed":
        if (
            not result.provider_call_attempted
            or result.provider_call_succeeded
            or result.result_validation != "not_attempted"
            or result.report is not None
        ):
            raise ModuleOperationsContractError(
                "provider-failed result contains inconsistent invocation state."
            )
        return

    if result.code == "module_operations.result_invalid":
        if (
            not result.provider_call_attempted
            or not result.provider_call_succeeded
            or result.result_validation != "failed"
            or result.report is not None
        ):
            raise ModuleOperationsContractError(
                "invalid-result outcome contains inconsistent invocation state."
            )
        return

    if (
        not result.provider_call_attempted
        or not result.provider_call_succeeded
        or result.result_validation != "passed"
        or result.report is None
    ):
        raise ModuleOperationsContractError(
            "successful invocation result contains inconsistent invocation state."
        )

    if result.capability == "readiness":
        if not isinstance(result.report, ModuleReadinessReport):
            raise ModuleOperationsContractError(
                "readiness invocation result must contain ModuleReadinessReport."
            )
    elif not isinstance(result.report, ModuleAttentionReport):
        raise ModuleOperationsContractError(
            "attention invocation result must contain ModuleAttentionReport."
        )

    expected_evaluation = (
        "unavailable"
        if result.code == "module_operations.evaluation_unavailable"
        else "evaluated"
    )
    if result.report.evaluation != expected_evaluation:
        raise ModuleOperationsContractError(
            "invocation result code does not match report evaluation."
        )


def _validate_request_fields(request: ModuleOperationsRequest) -> None:
    if request.workspace_root is not None:
        if not isinstance(request.workspace_root, Path):
            raise ModuleOperationsContractError(
                "workspace_root must be a pathlib.Path when provided."
            )
        if not request.workspace_root.is_absolute():
            raise ModuleOperationsContractError(
                "workspace_root must be absolute when provided."
            )

    if request.active_school_year is not None:
        _validated_school_year(request.active_school_year)

    if request.class_id is not None:
        _validate_identifier(request.class_id, "class_id")



def _validated_school_year(value: object) -> str:
    try:
        return validate_school_year(value)
    except SchoolYearValidationError as error:
        raise ModuleOperationsContractError(str(error)) from error

def _validate_attention_summary_fields(summary: ModuleAttentionSummary) -> None:
    _validate_bounded_identifier(summary.code, "code")
    _validate_safe_text(
        summary.label,
        "label",
        max_length=MAX_MODULE_OPERATION_LABEL_LENGTH,
    )

    if summary.count is not None:
        if isinstance(summary.count, bool) or not isinstance(summary.count, int):
            raise ModuleOperationsContractError(
                "count must be an integer when provided."
            )
        if not 0 <= summary.count <= MAX_MODULE_OPERATION_COUNT:
            raise ModuleOperationsContractError(
                f"count must be between 0 and {MAX_MODULE_OPERATION_COUNT}."
            )

    if summary.class_id is not None:
        _validate_identifier(summary.class_id, "class_id")

    if summary.work_ref is not None:
        if not isinstance(summary.work_ref, ModuleWorkRef):
            raise ModuleOperationsContractError(
                "work_ref must be a ModuleWorkRef when provided."
            )
        validate_module_work_ref(summary.work_ref)
        if (
            summary.class_id is not None
            and summary.class_id != summary.work_ref.class_id
        ):
            raise ModuleOperationsContractError(
                "class_id must match work_ref.class_id when both are provided."
            )

    if summary.action is not None:
        _require_action_ref(summary.action)


def _validate_readiness_report_fields(report: ModuleReadinessReport) -> None:
    _validate_evaluation(report.evaluation)
    _validate_notice_collection(report.notices)

    if report.evaluation == "evaluated":
        if not isinstance(report.ready, bool):
            raise ModuleOperationsContractError(
                "ready must be boolean when readiness was evaluated."
            )
        return

    if report.ready is not None:
        raise ModuleOperationsContractError(
            "ready must be None when readiness evaluation is unavailable."
        )


def _validate_attention_report_fields(report: ModuleAttentionReport) -> None:
    _validate_evaluation(report.evaluation)
    _validate_attention_collection(report.summaries)
    _validate_notice_collection(report.notices)

    if report.evaluation == "unavailable" and report.summaries:
        raise ModuleOperationsContractError(
            "attention summaries must be empty when evaluation is unavailable."
        )


def _validate_profile_fields(profile: ModuleOperationsProfile) -> None:
    _validate_lowercase_identifier(profile.module_id, "module_id")
    _validate_contract_versions(profile.supported_core_operations_contract_versions)

    if profile.readiness_provider is not None and not callable(
        profile.readiness_provider
    ):
        raise ModuleOperationsContractError(
            "readiness_provider must be callable when provided."
        )
    if profile.attention_provider is not None and not callable(
        profile.attention_provider
    ):
        raise ModuleOperationsContractError(
            "attention_provider must be callable when provided."
        )
    if profile.readiness_provider is None and profile.attention_provider is None:
        raise ModuleOperationsContractError(
            "profile must expose at least one operations capability."
        )


def _validate_report_owner(
    notices: tuple[ModuleOperationsNotice, ...],
    summaries: tuple[ModuleAttentionSummary, ...],
    expected_module_id: str | None,
) -> None:
    if expected_module_id is None:
        return
    _validate_lowercase_identifier(expected_module_id, "expected_module_id")

    for notice in notices:
        if notice.action is not None:
            validate_module_owner_action_ref(
                notice.action,
                expected_module_id=expected_module_id,
            )

    for summary in summaries:
        if summary.work_ref is not None:
            if summary.work_ref.module_id != expected_module_id:
                raise ModuleOperationsContractError(
                    "work_ref.module_id must match the owning module_id."
                )
        if summary.action is not None:
            validate_module_owner_action_ref(
                summary.action,
                expected_module_id=expected_module_id,
            )


def _validate_evaluation(value: object) -> None:
    if not isinstance(value, str) or value not in {"evaluated", "unavailable"}:
        raise ModuleOperationsContractError(
            "evaluation must be 'evaluated' or 'unavailable'."
        )


def _validate_notice_collection(
    notices: tuple[ModuleOperationsNotice, ...],
) -> None:
    if len(notices) > MAX_MODULE_OPERATIONS_NOTICES:
        raise ModuleOperationsContractError(
            "readiness/attention notices exceed the shared result bound."
        )
    for notice in notices:
        if not isinstance(notice, ModuleOperationsNotice):
            raise ModuleOperationsContractError(
                "notices must contain ModuleOperationsNotice values."
            )
        _validate_bounded_identifier(notice.code, "notice.code")
        _validate_safe_text(
            notice.summary,
            "notice.summary",
            max_length=MAX_MODULE_OPERATION_SUMMARY_LENGTH,
        )
        if notice.action is not None:
            _require_action_ref(notice.action)


def _validate_attention_collection(
    summaries: tuple[ModuleAttentionSummary, ...],
) -> None:
    if len(summaries) > MAX_MODULE_ATTENTION_SUMMARIES:
        raise ModuleOperationsContractError(
            "attention summaries exceed the shared result bound."
        )
    for summary in summaries:
        if not isinstance(summary, ModuleAttentionSummary):
            raise ModuleOperationsContractError(
                "summaries must contain ModuleAttentionSummary values."
            )
        _validate_attention_summary_fields(summary)


def _freeze_contract_versions(value: object) -> frozenset[str]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise ModuleOperationsContractError(
            "supported_core_operations_contract_versions must be an iterable "
            "of identifiers."
        )
    items = cast(Iterable[object], value)
    frozen: set[str] = set()
    for item in items:
        if not isinstance(item, str):
            raise ModuleOperationsContractError(
                "supported_core_operations_contract_versions must contain strings."
            )
        frozen.add(_validate_identifier(item, "operations contract version"))
    result = frozenset(frozen)
    _validate_contract_versions(result)
    return result


def _validate_contract_versions(versions: frozenset[str]) -> None:
    if not isinstance(versions, frozenset):
        raise ModuleOperationsContractError(
            "supported_core_operations_contract_versions must be a frozenset."
        )
    if not versions:
        raise ModuleOperationsContractError(
            "supported_core_operations_contract_versions must not be empty."
        )
    for version in versions:
        _validate_identifier(version, "operations contract version")


def _require_action_ref(action: object) -> ModuleOwnerActionRef:
    if not isinstance(action, ModuleOwnerActionRef):
        raise ModuleOperationsContractError(
            "action must be a ModuleOwnerActionRef when provided."
        )
    return validate_module_owner_action_ref(action)


def _validate_bounded_identifier(value: object, field_name: str) -> str:
    validated = _validate_lowercase_identifier(value, field_name)
    if len(validated) > MAX_MODULE_OPERATION_CODE_LENGTH:
        raise ModuleOperationsContractError(
            f"{field_name} must not exceed "
            f"{MAX_MODULE_OPERATION_CODE_LENGTH} characters."
        )
    return validated


def _validate_lowercase_identifier(value: object, field_name: str) -> str:
    validated = _validate_identifier(value, field_name)
    if validated != validated.lower():
        raise ModuleOperationsContractError(
            f"{field_name} must use lowercase characters."
        )
    return validated


def _validate_identifier(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise ModuleOperationsContractError(f"{field_name} must be a string.")
    try:
        return validate_identifier(value, field_name)
    except IdentifierValidationError as error:
        raise ModuleOperationsContractError(str(error)) from error


def _validate_safe_text(
    value: object,
    field_name: str,
    *,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        raise ModuleOperationsContractError(f"{field_name} must be a string.")
    if not value or value != value.strip():
        raise ModuleOperationsContractError(
            f"{field_name} must be nonblank without surrounding whitespace."
        )
    if len(value) > max_length:
        raise ModuleOperationsContractError(
            f"{field_name} must not exceed {max_length} characters."
        )
    if any(
        unicodedata.category(character) in {"Cc", "Zl", "Zp"}
        for character in value
    ):
        raise ModuleOperationsContractError(
            f"{field_name} must not contain control or line-separator characters."
        )
    return value
