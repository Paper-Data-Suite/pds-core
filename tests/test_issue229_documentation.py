"""Core #229 Slice 5: public documentation and executable API examples."""

from __future__ import annotations

import re
from pathlib import Path

from pds_core.publication_compatibility import (
    PublicationProducerProfile,
    PublicationReaderSupport,
    lookup_publication_reader_support,
)

ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "publication_reader_contract_metadata.md"
README_PATH = ROOT / "README.md"


def test_readme_links_authoritative_reader_contract_documentation() -> None:
    readme = README_PATH.read_text(encoding="utf-8")
    assert "[docs/publication_reader_contract_metadata.md]" in readme
    assert "(docs/publication_reader_contract_metadata.md)" in readme
    assert DOC_PATH.is_file()


def test_documented_examples_execute_against_current_core_public_api() -> None:
    document = DOC_PATH.read_text(encoding="utf-8")
    python_blocks = re.findall(r"```python\n(.*?)\n```", document, flags=re.DOTALL)
    assert len(python_blocks) == 1
    namespace: dict[str, object] = {"__name__": "_issue229_documented_example"}
    exec(compile(python_blocks[0], str(DOC_PATH), "exec"), namespace)
    academic = namespace["scoreform_profile"]
    intervention = namespace["portia_profile"]
    assert isinstance(academic, PublicationProducerProfile)
    assert isinstance(intervention, PublicationProducerProfile)
    assert intervention.supported_academic_work_contract_versions == frozenset()
    assert academic.publication_contracts[0].publication_kind == "academic_result_set"
    assert intervention.publication_contracts[0].publication_kind == "intervention_record_set"
    academic_reader = lookup_publication_reader_support(
        academic,
        "academic_result_set",
        "scoreform_academic_result_manifest_v1",
    )
    intervention_reader = lookup_publication_reader_support(
        intervention,
        "intervention_record_set",
        "portia_intervention_manifest_v1",
    )
    assert isinstance(academic_reader, PublicationReaderSupport)
    assert isinstance(intervention_reader, PublicationReaderSupport)
    assert academic_reader.distribution_name == "scoreform"
    assert intervention_reader.distribution_name == "pds-portia"
    assert lookup_publication_reader_support(
        intervention,
        "academic_result_set",
        "portia_intervention_manifest_v1",
    ) is None


def test_documentation_preserves_contract_and_authority_distinctions() -> None:
    document = DOC_PATH.read_text(encoding="utf-8")
    for required in (
        "Meridian #111",
        "Vitrine #103",
        "Portia #66",
        "intervention_record_set",
        "academic_result_set",
        "paper_data_suite.publication_producers",
        "PublicationReaderSupport",
        "PublicationContractSupport.reader_support",
        "PublicationProducerProfileError",
        "evaluate_publication_compatibility(...)",
        "lookup_publication_reader_support(profile, publication_kind, "
        "manifest_contract_version)",
        "bounded exact-version legacy qualification list",
        "reader_support=()",
        "not imported or called",
        "fail closed",
        "source-read authorization",
        "Core 0.6.4",
    ):
        assert required in document, f"Missing issue #229 contract coverage: {required}"
    assert "**not** an API claim" in document
