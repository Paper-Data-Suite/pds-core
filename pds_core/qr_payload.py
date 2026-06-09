"""Shared QR payload data model for Paper Data Suite."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from pds_core.identifiers import IdentifierValidationError, validate_identifier

RESERVED_METADATA_KEYS = {
    "schema",
    "module",
    "class",
    "class_id",
    "aid",
    "assignment_id",
    "sid",
    "student_id",
    "page",
}


class QrPayloadValidationError(ValueError):
    """Raised when normalized QR payload data is invalid."""


@dataclass(frozen=True)
class QrPayload:
    """Normalized QR payload metadata used by Paper Data Suite modules."""

    schema: str
    module: str
    class_id: str
    assignment_id: str
    student_id: str
    page: int
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate normalized QR payload fields."""
        self._validate_identifier_field(self.schema, "schema")
        self._validate_identifier_field(self.module, "module")
        self._validate_identifier_field(self.class_id, "class_id")
        self._validate_identifier_field(self.assignment_id, "assignment_id")
        self._validate_identifier_field(self.student_id, "student_id")
        self._validate_page()
        self._validate_metadata()

    @staticmethod
    def _validate_identifier_field(value: str, field_name: str) -> None:
        """Validate one identifier-like QR payload field."""
        try:
            validate_identifier(value, field_name)
        except IdentifierValidationError as error:
            raise QrPayloadValidationError(str(error)) from error

    def _validate_page(self) -> None:
        """Validate the page number."""
        if not isinstance(self.page, int):
            raise QrPayloadValidationError("page must be an integer.")

        if self.page < 1:
            raise QrPayloadValidationError("page must be greater than or equal to 1.")

    def _validate_metadata(self) -> None:
        """Validate optional QR payload metadata."""
        if not isinstance(self.metadata, Mapping):
            raise QrPayloadValidationError("metadata must be a mapping.")

        for key, value in self.metadata.items():
            if not isinstance(key, str):
                raise QrPayloadValidationError("metadata keys must be strings.")

            if not isinstance(value, str):
                raise QrPayloadValidationError("metadata values must be strings.")

            if key in RESERVED_METADATA_KEYS:
                raise QrPayloadValidationError(
                    f"metadata key '{key}' is reserved and must not be used."
                )

            self._validate_identifier_field(key, f"metadata key '{key}'")
            self._validate_identifier_field(value, f"metadata value for '{key}'")