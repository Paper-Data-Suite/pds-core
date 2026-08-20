"""Failure-isolating diagnostics for Core-defined provider entry points."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, replace
from importlib import metadata
from typing import Final, Literal, TypeAlias

from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.module_profiles import (
    CORE_ROUTING_CONTRACT_VERSION,
    MODULE_PROFILE_ENTRY_POINT_GROUP,
    ModuleProfile,
    validate_module_profile,
)
from pds_core.publication_compatibility import (
    PUBLICATION_PRODUCER_ENTRY_POINT_GROUP,
    PublicationProducerProfile,
    validate_publication_producer_profile,
)
from pds_core.publication_records import PUBLICATION_RECORD_SCHEMA_VERSION


ProviderKind: TypeAlias = Literal["routing_module", "publication_producer"]
ProviderDiagnosticStage: TypeAlias = Literal[
    "metadata",
    "load",
    "call",
    "profile_validation",
    "identity_validation",
    "compatibility",
    "registry_conflict",
    "valid",
]
ProviderCheckOutcome: TypeAlias = Literal["not_attempted", "passed", "failed"]
ProviderDiagnosticCode: TypeAlias = Literal[
    "provider.entry_point_name_invalid",
    "provider.load_failed",
    "provider.not_callable",
    "provider.call_failed",
    "provider.profile_invalid",
    "provider.identity_mismatch",
    "provider.core_incompatible",
    "provider.identity_conflict",
    "provider.valid",
]
ProviderProfile: TypeAlias = ModuleProfile | PublicationProducerProfile

_PROVIDER_KINDS: Final[tuple[ProviderKind, ...]] = (
    "routing_module",
    "publication_producer",
)
_PROVIDER_GROUPS: Final[dict[ProviderKind, str]] = {
    "routing_module": MODULE_PROFILE_ENTRY_POINT_GROUP,
    "publication_producer": PUBLICATION_PRODUCER_ENTRY_POINT_GROUP,
}
_PROVIDER_KIND_ORDER: Final[dict[ProviderKind, int]] = {
    kind: index for index, kind in enumerate(_PROVIDER_KINDS)
}
_ENTRY_POINT_NAME_DISPLAY_LIMIT: Final[int] = 256
_ENTRY_POINT_TARGET_DISPLAY_LIMIT: Final[int] = 1024
_DISTRIBUTION_NAME_DISPLAY_LIMIT: Final[int] = 256
_METADATA_TRUNCATION_MARKER: Final[str] = "\N{HORIZONTAL ELLIPSIS}"


class ProviderDiagnosticsError(RuntimeError):
    """Base error for provider diagnostic operations."""


class ProviderEnumerationError(ProviderDiagnosticsError):
    """Raised when installed entry-point metadata cannot be enumerated."""


class ProviderDiagnosticRequestError(ProviderDiagnosticsError):
    """Raised when a diagnostic request names an unsupported provider kind."""


@dataclass(frozen=True, slots=True)
class ProviderEntryPointMetadata:
    """Safe metadata for one Core-defined provider entry point."""

    provider_kind: ProviderKind
    entry_point_group: str
    entry_point_name: str
    entry_point_target: str
    distribution_name: str | None


@dataclass(frozen=True, slots=True)
class ProviderDiagnosticResult:
    """One independent diagnostic outcome for one installed provider candidate."""

    metadata: ProviderEntryPointMetadata
    stage: ProviderDiagnosticStage
    code: ProviderDiagnosticCode
    message: str
    load_attempted: bool
    load_succeeded: bool
    provider_call_attempted: bool
    provider_call_succeeded: bool
    declared_identity: str | None
    profile_validation: ProviderCheckOutcome
    core_compatibility: ProviderCheckOutcome
    registry_conflict: bool
    validated_profile: ProviderProfile | None = None


@dataclass(frozen=True, slots=True)
class _ProviderCandidate:
    metadata: ProviderEntryPointMetadata
    raw_entry_point_name: object
    entry_point: object


@dataclass(frozen=True, slots=True)
class _ValidatedCandidate:
    result_index: int
    provider_kind: ProviderKind
    identity: str


def inspect_core_provider_entry_points(
    *,
    provider_kind: ProviderKind | None = None,
) -> tuple[ProviderEntryPointMetadata, ...]:
    """Inspect provider metadata without loading optional provider code."""
    return tuple(
        candidate.metadata
        for candidate in _enumerate_provider_candidates(provider_kind=provider_kind)
    )


def diagnose_core_providers(
    *,
    provider_kind: ProviderKind | None = None,
) -> tuple[ProviderDiagnosticResult, ...]:
    """Load and validate installed provider candidates independently."""
    candidates = _enumerate_provider_candidates(provider_kind=provider_kind)
    results: list[ProviderDiagnosticResult] = []
    validated_candidates: list[_ValidatedCandidate] = []

    for candidate in candidates:
        result, registry_identity = _diagnose_candidate(candidate)
        results.append(result)
        if registry_identity is not None:
            validated_candidates.append(
                _ValidatedCandidate(
                    result_index=len(results) - 1,
                    provider_kind=result.metadata.provider_kind,
                    identity=registry_identity,
                )
            )

    conflicts: dict[tuple[ProviderKind, str], list[int]] = {}
    for validated_candidate in validated_candidates:
        key = (validated_candidate.provider_kind, validated_candidate.identity)
        conflicts.setdefault(key, []).append(validated_candidate.result_index)

    for result_indexes in conflicts.values():
        if len(result_indexes) < 2:
            continue
        for result_index in result_indexes:
            current = results[result_index]
            results[result_index] = replace(
                current,
                stage="registry_conflict",
                code="provider.identity_conflict",
                message=(
                    "Candidate conflicts with another validated provider "
                    "claiming the same Core identity."
                ),
                registry_conflict=True,
                validated_profile=None,
            )

    return tuple(results)


def _diagnose_candidate(
    candidate: _ProviderCandidate,
) -> tuple[ProviderDiagnosticResult, str | None]:
    metadata_row = candidate.metadata
    entry_point_name = candidate.raw_entry_point_name

    if not _entry_point_name_is_valid(entry_point_name):
        return (
            _result(
                metadata_row,
                stage="identity_validation",
                code="provider.entry_point_name_invalid",
                message=(
                    "Entry-point name is not a valid lowercase Core provider "
                    "identity."
                ),
            ),
            None,
        )

    assert isinstance(entry_point_name, str)

    try:
        load = getattr(candidate.entry_point, "load")
        provider = load()
    except Exception:
        return (
            _result(
                metadata_row,
                stage="load",
                code="provider.load_failed",
                message="Entry-point object could not be loaded.",
                load_attempted=True,
            ),
            None,
        )

    if not callable(provider):
        return (
            _result(
                metadata_row,
                stage="load",
                code="provider.not_callable",
                message="Loaded entry-point object is not callable.",
                load_attempted=True,
                load_succeeded=True,
            ),
            None,
        )

    try:
        raw_profile = provider()
    except Exception:
        return (
            _result(
                metadata_row,
                stage="call",
                code="provider.call_failed",
                message="Provider callable raised while producing its profile.",
                load_attempted=True,
                load_succeeded=True,
                provider_call_attempted=True,
            ),
            None,
        )

    try:
        validated = _validate_profile(metadata_row.provider_kind, raw_profile)
    except Exception:
        return (
            _result(
                metadata_row,
                stage="profile_validation",
                code="provider.profile_invalid",
                message="Provider returned an invalid Core profile.",
                load_attempted=True,
                load_succeeded=True,
                provider_call_attempted=True,
                provider_call_succeeded=True,
                profile_validation="failed",
            ),
            None,
        )

    declared_identity = validated.module_id
    if entry_point_name != declared_identity:
        return (
            _result(
                metadata_row,
                stage="identity_validation",
                code="provider.identity_mismatch",
                message=(
                    "Entry-point name does not match the validated provider "
                    "identity."
                ),
                load_attempted=True,
                load_succeeded=True,
                provider_call_attempted=True,
                provider_call_succeeded=True,
                declared_identity=declared_identity,
                profile_validation="passed",
            ),
            None,
        )

    if not _profile_supports_active_core(metadata_row.provider_kind, validated):
        return (
            _result(
                metadata_row,
                stage="compatibility",
                code="provider.core_incompatible",
                message=_incompatibility_message(metadata_row.provider_kind),
                load_attempted=True,
                load_succeeded=True,
                provider_call_attempted=True,
                provider_call_succeeded=True,
                declared_identity=declared_identity,
                profile_validation="passed",
                core_compatibility="failed",
            ),
            declared_identity,
        )

    return (
        _result(
            metadata_row,
            stage="valid",
            code="provider.valid",
            message="Provider satisfies the active Core contract.",
            load_attempted=True,
            load_succeeded=True,
            provider_call_attempted=True,
            provider_call_succeeded=True,
            declared_identity=declared_identity,
            profile_validation="passed",
            core_compatibility="passed",
            validated_profile=validated,
        ),
        declared_identity,
    )


def _enumerate_provider_candidates(
    *,
    provider_kind: ProviderKind | None,
) -> tuple[_ProviderCandidate, ...]:
    candidates: list[_ProviderCandidate] = []

    for kind in _requested_provider_kinds(provider_kind):
        group = _PROVIDER_GROUPS[kind]
        try:
            entry_points = metadata.entry_points(group=group)
            group_candidates = [
                _candidate_from_entry_point(kind, group, entry_point)
                for entry_point in entry_points
            ]
        except Exception as error:
            raise ProviderEnumerationError(
                f"Could not enumerate installed provider metadata for {group!r}."
            ) from error
        candidates.extend(group_candidates)

    return tuple(
        sorted(
            candidates,
            key=lambda candidate: (
                _PROVIDER_KIND_ORDER[candidate.metadata.provider_kind],
                candidate.metadata.entry_point_name,
                candidate.metadata.entry_point_target,
                candidate.metadata.distribution_name or "",
            ),
        )
    )


def _requested_provider_kinds(
    provider_kind: ProviderKind | None,
) -> tuple[ProviderKind, ...]:
    if provider_kind is None:
        return _PROVIDER_KINDS
    if provider_kind not in _PROVIDER_KINDS:
        raise ProviderDiagnosticRequestError(
            f"Unsupported provider_kind {provider_kind!r}."
        )
    return (provider_kind,)


def _candidate_from_entry_point(
    provider_kind: ProviderKind,
    group: str,
    entry_point: object,
) -> _ProviderCandidate:
    raw_name = _safe_attribute(entry_point, "name")
    return _ProviderCandidate(
        metadata=ProviderEntryPointMetadata(
            provider_kind=provider_kind,
            entry_point_group=group,
            entry_point_name=_safe_metadata_text(
                raw_name,
                unavailable="<invalid-name>",
                max_length=_ENTRY_POINT_NAME_DISPLAY_LIMIT,
            ),
            entry_point_target=_safe_metadata_text(
                _safe_attribute(entry_point, "value"),
                unavailable="<unavailable>",
                max_length=_ENTRY_POINT_TARGET_DISPLAY_LIMIT,
            ),
            distribution_name=_distribution_name(entry_point),
        ),
        raw_entry_point_name=raw_name,
        entry_point=entry_point,
    )


def _safe_attribute(value: object, name: str) -> object:
    try:
        return getattr(value, name)
    except Exception:
        return None


def _distribution_name(entry_point: object) -> str | None:
    distribution = _safe_attribute(entry_point, "dist")
    if distribution is None:
        return None

    name = _safe_attribute(distribution, "name")
    if not isinstance(name, str):
        distribution_metadata = _safe_attribute(distribution, "metadata")
        metadata_get = _safe_attribute(distribution_metadata, "get")
        if callable(metadata_get):
            try:
                name = metadata_get("Name")
            except Exception:
                name = None

    if not isinstance(name, str) or not name:
        return None
    return _safe_metadata_text(
        name,
        unavailable="<unavailable>",
        max_length=_DISTRIBUTION_NAME_DISPLAY_LIMIT,
    )


def _safe_metadata_text(
    value: object,
    *,
    unavailable: str,
    max_length: int,
) -> str:
    if not isinstance(value, str):
        return unavailable
    sanitized = "".join(
        character
        if unicodedata.category(character) not in {"Cc", "Zl", "Zp"}
        else "\N{REPLACEMENT CHARACTER}"
        for character in value
    )
    if len(sanitized) <= max_length:
        return sanitized
    return sanitized[: max_length - 1] + _METADATA_TRUNCATION_MARKER


def _entry_point_name_is_valid(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        validated = validate_identifier(value, "entry point name")
    except IdentifierValidationError:
        return False
    return validated == validated.lower()


def _validate_profile(provider_kind: ProviderKind, value: object) -> ProviderProfile:
    if provider_kind == "routing_module":
        if not isinstance(value, ModuleProfile):
            raise TypeError("routing provider returned a non-ModuleProfile value")
        return validate_module_profile(value)

    if not isinstance(value, PublicationProducerProfile):
        raise TypeError(
            "publication provider returned a non-PublicationProducerProfile value"
        )
    return validate_publication_producer_profile(value)


def _profile_supports_active_core(
    provider_kind: ProviderKind,
    profile: ProviderProfile,
) -> bool:
    if provider_kind == "routing_module":
        if not isinstance(profile, ModuleProfile):
            return False
        return (
            CORE_ROUTING_CONTRACT_VERSION
            in profile.supported_core_routing_contract_versions
        )

    if not isinstance(profile, PublicationProducerProfile):
        return False
    return (
        PUBLICATION_RECORD_SCHEMA_VERSION
        in profile.supported_core_publication_schema_versions
    )


def _incompatibility_message(provider_kind: ProviderKind) -> str:
    if provider_kind == "routing_module":
        return (
            "Validated provider does not support active Core routing contract "
            f"{CORE_ROUTING_CONTRACT_VERSION!r}."
        )
    return (
        "Validated provider does not support active Core Publication Record "
        f"schema {PUBLICATION_RECORD_SCHEMA_VERSION!r}."
    )


def _result(
    metadata_row: ProviderEntryPointMetadata,
    *,
    stage: ProviderDiagnosticStage,
    code: ProviderDiagnosticCode,
    message: str,
    load_attempted: bool = False,
    load_succeeded: bool = False,
    provider_call_attempted: bool = False,
    provider_call_succeeded: bool = False,
    declared_identity: str | None = None,
    profile_validation: ProviderCheckOutcome = "not_attempted",
    core_compatibility: ProviderCheckOutcome = "not_attempted",
    registry_conflict: bool = False,
    validated_profile: ProviderProfile | None = None,
) -> ProviderDiagnosticResult:
    return ProviderDiagnosticResult(
        metadata=metadata_row,
        stage=stage,
        code=code,
        message=message,
        load_attempted=load_attempted,
        load_succeeded=load_succeeded,
        provider_call_attempted=provider_call_attempted,
        provider_call_succeeded=provider_call_succeeded,
        declared_identity=declared_identity,
        profile_validation=profile_validation,
        core_compatibility=core_compatibility,
        registry_conflict=registry_conflict,
        validated_profile=validated_profile,
    )
