"""Module-neutral producer compatibility metadata for Publication Records."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from importlib import metadata
import re
from typing import Final, cast

from pds_core.academic_work_registrations import (
    AcademicWorkRegistration,
    validate_academic_work_registration,
)
from pds_core.identifiers import IdentifierValidationError, validate_identifier
from pds_core.publication_records import (
    PublicationCapability,
    PublicationKind,
    PublicationRecord,
    is_publication_capability,
    is_publication_kind,
    validate_publication_record,
)

CORE_PUBLICATION_COMPATIBILITY_CONTRACT_VERSION: Final[str] = "1"
PUBLICATION_PRODUCER_ENTRY_POINT_GROUP: Final[str] = (
    "paper_data_suite.publication_producers"
)
_COMPATIBILITY_CODE: Final[re.Pattern[str]] = re.compile(
    r"^contracts\.[a-z][a-z0-9_]*$"
)


class PublicationCompatibilityError(RuntimeError):
    """Base error for publication compatibility metadata."""


class PublicationProducerProfileError(PublicationCompatibilityError, ValueError):
    """Raised when producer compatibility metadata is invalid."""


class PublicationProducerDiscoveryError(PublicationCompatibilityError):
    """Raised when installed producer profile discovery fails."""


class PublicationProducerRegistryError(PublicationCompatibilityError):
    """Raised when producer profiles cannot form one unambiguous registry."""


def _identifier(value: object, name: str, *, lowercase: bool = False) -> str:
    if not isinstance(value, str):
        raise PublicationProducerProfileError(f"{name} must be a string.")
    try:
        result = validate_identifier(value, name)
    except IdentifierValidationError as error:
        raise PublicationProducerProfileError(str(error)) from error
    if lowercase and result != result.lower():
        raise PublicationProducerProfileError(f"{name} must be lowercase.")
    return result


def _versions(value: object, name: str) -> frozenset[str]:
    if isinstance(value, (str, bytes, Mapping)):
        raise PublicationProducerProfileError(f"{name} must be an iterable of versions.")
    try:
        result = frozenset(
            _identifier(item, name) for item in cast(Iterable[object], value)
        )
    except TypeError as error:
        raise PublicationProducerProfileError(f"{name} must be iterable.") from error
    if not result:
        raise PublicationProducerProfileError(f"{name} must not be empty.")
    return result


@dataclass(frozen=True, slots=True)
class SourceRecordContractSupport:
    record_kind: str
    contract_versions: frozenset[str]
    allows_unversioned: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_kind", _identifier(self.record_kind, "record_kind", lowercase=True))
        object.__setattr__(self, "contract_versions", _versions(self.contract_versions, "contract_versions"))
        if not isinstance(self.allows_unversioned, bool):
            raise PublicationProducerProfileError("allows_unversioned must be boolean.")


@dataclass(frozen=True, slots=True)
class PublicationContractSupport:
    publication_kind: PublicationKind
    manifest_contract_versions: frozenset[str]
    supported_capabilities: frozenset[PublicationCapability]
    source_record_contracts: tuple[SourceRecordContractSupport, ...] = ()
    allows_missing_source_record: bool = True

    def __post_init__(self) -> None:
        if not is_publication_kind(self.publication_kind):
            raise PublicationProducerProfileError("publication_kind is invalid.")
        object.__setattr__(self, "manifest_contract_versions", _versions(self.manifest_contract_versions, "manifest_contract_versions"))
        if isinstance(self.supported_capabilities, (str, bytes, Mapping)):
            raise PublicationProducerProfileError("supported_capabilities must be an iterable.")
        if isinstance(self.source_record_contracts, (str, bytes, Mapping)):
            raise PublicationProducerProfileError(
                "source_record_contracts must be an iterable."
            )
        try:
            capabilities = frozenset(self.supported_capabilities)
        except TypeError as error:
            raise PublicationProducerProfileError("supported_capabilities must be iterable.") from error
        if any(not is_publication_capability(value) for value in capabilities):
            raise PublicationProducerProfileError("supported_capabilities contains an invalid capability.")
        object.__setattr__(self, "supported_capabilities", capabilities)
        try:
            rows = tuple(self.source_record_contracts)
        except TypeError as error:
            raise PublicationProducerProfileError("source_record_contracts must be iterable.") from error
        if any(not isinstance(row, SourceRecordContractSupport) for row in rows):
            raise PublicationProducerProfileError("source_record_contracts contains an invalid row.")
        rows = tuple(sorted(rows, key=lambda row: row.record_kind))
        if len({row.record_kind for row in rows}) != len(rows):
            raise PublicationProducerProfileError("source_record_contracts contains duplicate record_kind support.")
        object.__setattr__(self, "source_record_contracts", rows)
        if not isinstance(self.allows_missing_source_record, bool):
            raise PublicationProducerProfileError("allows_missing_source_record must be boolean.")


@dataclass(frozen=True, slots=True)
class PublicationProducerProfile:
    module_id: str
    display_name: str
    supported_core_publication_schema_versions: frozenset[str]
    supported_academic_work_contract_versions: frozenset[str]
    publication_contracts: tuple[PublicationContractSupport, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "module_id", _identifier(self.module_id, "module_id", lowercase=True))
        if (
            not isinstance(self.display_name, str)
            or not self.display_name.strip()
            or self.display_name != self.display_name.strip()
            or any(
                ord(character) < 32
                or ord(character) == 127
                or character in {"\u2028", "\u2029"}
                for character in self.display_name
            )
        ):
            raise PublicationProducerProfileError(
                "display_name must be a nonempty trimmed single-line string without control characters."
            )
        object.__setattr__(self, "supported_core_publication_schema_versions", _versions(self.supported_core_publication_schema_versions, "supported_core_publication_schema_versions"))
        object.__setattr__(self, "supported_academic_work_contract_versions", _versions(self.supported_academic_work_contract_versions, "supported_academic_work_contract_versions"))
        if isinstance(self.publication_contracts, (str, bytes, Mapping)):
            raise PublicationProducerProfileError(
                "publication_contracts must be an iterable."
            )
        try:
            contracts = tuple(self.publication_contracts)
        except TypeError as error:
            raise PublicationProducerProfileError("publication_contracts must be iterable.") from error
        if not contracts or any(not isinstance(row, PublicationContractSupport) for row in contracts):
            raise PublicationProducerProfileError("publication_contracts must contain valid support rows.")
        contracts = tuple(sorted(contracts, key=lambda row: row.publication_kind))
        if len({row.publication_kind for row in contracts}) != len(contracts):
            raise PublicationProducerProfileError("publication_contracts contains duplicate publication_kind support.")
        object.__setattr__(self, "publication_contracts", contracts)


@dataclass(frozen=True, slots=True)
class PublicationProducerRegistry:
    profiles: tuple[PublicationProducerProfile, ...]

    def __post_init__(self) -> None:
        if isinstance(self.profiles, (str, bytes, Mapping)):
            raise PublicationProducerRegistryError("profiles must be an iterable of profiles.")
        try:
            raw_profiles = tuple(self.profiles)
        except TypeError as error:
            raise PublicationProducerRegistryError("profiles must be iterable.") from error
        if any(not isinstance(value, PublicationProducerProfile) for value in raw_profiles):
            raise PublicationProducerRegistryError(
                "profiles contains a non-Profile value."
            )
        profiles = tuple(
            sorted(
                (validate_publication_producer_profile(value) for value in raw_profiles),
                key=lambda value: value.module_id,
            )
        )
        if len({value.module_id for value in profiles}) != len(profiles):
            raise PublicationProducerRegistryError("duplicate producer module_id.")
        object.__setattr__(self, "profiles", profiles)

    def get(self, module_id: str) -> PublicationProducerProfile | None:
        validated = _identifier(module_id, "module_id", lowercase=True)
        return next((profile for profile in self.profiles if profile.module_id == validated), None)


@dataclass(frozen=True, slots=True)
class PublicationCompatibilityResult:
    compatible: bool
    codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.compatible, bool):
            raise PublicationProducerProfileError("compatible must be boolean.")
        if isinstance(self.codes, (str, bytes, Mapping)):
            raise PublicationProducerProfileError("codes must be an iterable of codes.")
        try:
            raw_codes = tuple(self.codes)
        except TypeError as error:
            raise PublicationProducerProfileError("codes must be iterable.") from error
        if any(
            not isinstance(code, str)
            or _COMPATIBILITY_CODE.fullmatch(code) is None
            for code in raw_codes
        ):
            raise PublicationProducerProfileError(
                "codes must contain lowercase dotted contracts.* identifiers."
            )
        codes = tuple(sorted(set(raw_codes)))
        if self.compatible != (not codes):
            raise PublicationProducerProfileError(
                "compatible must agree with whether codes is empty."
            )
        object.__setattr__(self, "codes", codes)


def validate_publication_producer_profile(value: PublicationProducerProfile) -> PublicationProducerProfile:
    if not isinstance(value, PublicationProducerProfile):
        raise PublicationProducerProfileError("profile must be a PublicationProducerProfile.")
    return PublicationProducerProfile(
        module_id=value.module_id, display_name=value.display_name,
        supported_core_publication_schema_versions=value.supported_core_publication_schema_versions,
        supported_academic_work_contract_versions=value.supported_academic_work_contract_versions,
        publication_contracts=value.publication_contracts,
    )


def evaluate_publication_compatibility(
    publication: PublicationRecord,
    profile: PublicationProducerProfile,
    registration: AcademicWorkRegistration | None = None,
) -> PublicationCompatibilityResult:
    """Evaluate shared contract metadata without interpreting manifest contents."""
    if not isinstance(publication, PublicationRecord):
        raise PublicationProducerProfileError("publication must be a PublicationRecord.")
    try:
        checked_publication = validate_publication_record(publication)
    except ValueError as error:
        raise PublicationProducerProfileError(
            f"publication is invalid: {error}"
        ) from error
    validated = validate_publication_producer_profile(profile)
    codes: list[str] = []
    if checked_publication.work.module_id != validated.module_id:
        codes.append("contracts.profile_module_mismatch")
    if checked_publication.schema_version not in validated.supported_core_publication_schema_versions:
        codes.append("contracts.publication_schema_incompatible")
    checked_registration: AcademicWorkRegistration | None = None
    if registration is not None:
        try:
            checked_registration = validate_academic_work_registration(registration)
        except ValueError as error:
            raise PublicationProducerProfileError(
                f"registration is invalid: {error}"
            ) from error
        if checked_registration.work != checked_publication.work:
            raise PublicationProducerProfileError(
                "registration work does not match the Publication Record."
            )
        if (
            checked_publication.academic_work_registration_revision
            != checked_registration.registration_revision
        ):
            raise PublicationProducerProfileError(
                "registration revision does not match the Publication Record reference."
            )
    if checked_publication.publication_kind == "academic_result_set":
        if checked_registration is None or checked_registration.producer_contract_version not in validated.supported_academic_work_contract_versions:
            codes.append("contracts.registration_version_incompatible")
    elif checked_registration is not None:
        raise PublicationProducerProfileError(
            "intervention publications must not supply an Academic Work Registration."
        )
    support = next((row for row in validated.publication_contracts if row.publication_kind == checked_publication.publication_kind), None)
    if support is None:
        codes.append("contracts.publication_kind_incompatible")
    else:
        if checked_publication.manifest_contract_version not in support.manifest_contract_versions:
            codes.append("contracts.manifest_version_incompatible")
        if not set(checked_publication.capabilities).issubset(support.supported_capabilities):
            codes.append("contracts.capability_incompatible")
        source = checked_publication.source_record
        if source is None:
            if not support.allows_missing_source_record:
                codes.append("contracts.source_record_missing_incompatible")
        else:
            row = next((item for item in support.source_record_contracts if item.record_kind == source.record_kind), None)
            if row is None or source.module_id != validated.module_id:
                codes.append("contracts.source_record_kind_incompatible")
            elif source.contract_version is None:
                if not row.allows_unversioned:
                    codes.append("contracts.source_record_version_incompatible")
            elif source.contract_version not in row.contract_versions:
                codes.append("contracts.source_record_version_incompatible")
    return PublicationCompatibilityResult(compatible=not codes, codes=tuple(codes))


def discover_publication_producer_profiles() -> tuple[PublicationProducerProfile, ...]:
    try:
        points = metadata.entry_points().select(group=PUBLICATION_PRODUCER_ENTRY_POINT_GROUP)
        profiles: list[PublicationProducerProfile] = []
        for point in sorted(points, key=lambda value: value.name):
            entry_name = _identifier(point.name, "entry point name", lowercase=True)
            try:
                provider = point.load()
            except Exception as error:
                raise PublicationProducerDiscoveryError(
                    f"Could not load producer entry point {point.name!r}: {error}"
                ) from error
            if not callable(provider):
                raise PublicationProducerDiscoveryError(f"Producer entry point {point.name!r} is not callable.")
            try:
                discovered = validate_publication_producer_profile(provider())
            except Exception as error:
                raise PublicationProducerDiscoveryError(
                    f"Producer entry point {point.name!r} failed: {error}"
                ) from error
            if discovered.module_id != entry_name:
                raise PublicationProducerDiscoveryError(
                    f"Producer entry point {entry_name!r} returned profile "
                    f"{discovered.module_id!r}."
                )
            profiles.append(discovered)
        return PublicationProducerRegistry(tuple(profiles)).profiles
    except PublicationCompatibilityError:
        raise
    except Exception as error:
        raise PublicationProducerDiscoveryError(f"Could not discover producer profiles: {error}") from error


def build_publication_producer_registry(
    *, explicit_profiles: Iterable[PublicationProducerProfile] = (), discover_installed: bool = True,
) -> PublicationProducerRegistry:
    if not isinstance(discover_installed, bool):
        raise PublicationProducerRegistryError("discover_installed must be boolean.")
    try:
        profiles = tuple(explicit_profiles)
    except TypeError as error:
        raise PublicationProducerRegistryError("explicit_profiles must be iterable.") from error
    if discover_installed:
        profiles += discover_publication_producer_profiles()
    return PublicationProducerRegistry(profiles)
