"""Shared helpers for pds-core CLI tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.cli import main
from pds_core.standards import StandardDefinition, StandardsLibrary, StandardsProfile


def make_cli_library() -> StandardsLibrary:
    return StandardsLibrary(
        standards=(
            StandardDefinition(
                standard_id="njsls-ela:RL.CR.11-12.1",
                code="RL.CR.11-12.1",
                source="NJSLS-ELA",
                short_name="Close Reading Evidence",
                description="Cite strong and thorough textual evidence.",
                subject="English Language Arts",
                course="English 12",
                grade_band="11-12",
                domain="Reading Literature",
                category_path=(
                    "English Language Arts",
                    "Reading Literature",
                    "Close Reading",
                ),
                tags=("close_reading", "textual_evidence"),
                active=True,
                available_modules=("pds-scoreform", "pds-quillan"),
            ),
            StandardDefinition(
                standard_id="njsls-ela:RI.CR.11-12.1",
                code="RI.CR.11-12.1",
                source="NJSLS-ELA",
                short_name="Informational Text Evidence",
                description="Cite textual evidence from informational text.",
                subject="English Language Arts",
                course="English 12",
                grade_band="11-12",
                domain="Reading Informational Text",
                category_path=(
                    "English Language Arts",
                    "Reading Informational Text",
                    "Close Reading",
                ),
                tags=("informational_text",),
                active=False,
                available_modules=("pds-quillan",),
            ),
            StandardDefinition(
                standard_id="local-writing:evidence_explanation",
                code="evidence_explanation",
                source="Local Writing Rubric",
                short_name="Evidence Explanation",
                description="Explain how evidence supports a claim.",
                subject="English Language Arts",
                course="English 12",
                grade_band="11-12",
                domain="Writing",
                category_path=("English Language Arts", "Writing"),
                tags=("writing",),
                active=True,
                available_modules=("pds-scoreform",),
            ),
            StandardDefinition(
                standard_id="local-misc:unfiled",
                code="unfiled",
                source="Local Misc",
                short_name="Unfiled Skill",
                description="A local skill without subject or domain metadata.",
                active=True,
            ),
        ),
        profiles=(
            StandardsProfile(
                profile_id="english_12_njsls",
                standards=(
                    "njsls-ela:RL.CR.11-12.1",
                    "njsls-ela:RI.CR.11-12.1",
                ),
                subject="English Language Arts",
                course="English 12",
                source="NJSLS-ELA",
                title="English 12 NJSLS",
                description="NJSLS English 12 profile.",
            ),
            StandardsProfile(
                profile_id="english_12_local",
                standards=("local-writing:evidence_explanation",),
                subject="English Language Arts",
                course="English 12",
                source="Local Writing Rubric",
                title="English 12 Local Writing",
                description="Local writing profile.",
            ),
        ),
    )


def run_cli(
    tmp_path: Path,
    *args: str,
    capsys: pytest.CaptureFixture[str],
) -> tuple[int, str, str]:
    code = main(["--workspace", str(tmp_path), *args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def standard_mutation_args(
    *,
    include_standard_id: bool = True,
    standard_id: str = "local-reading:close_reading",
    code: str = "CR.1",
    short_name: str = "Close Reading",
    description: str = "Use evidence from a text.",
) -> list[str]:
    args = []
    if include_standard_id:
        args.extend(["--standard-id", standard_id])
    args.extend(
        [
            "--code",
            code,
            "--source",
            "Local Reading",
            "--short-name",
            short_name,
            "--description",
            description,
        ]
    )
    return args
