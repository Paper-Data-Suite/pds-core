from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_released_consumer_qualification_documentation_is_explicit() -> None:
    document = (ROOT / "docs" / "released_consumer_compatibility.md").read_text(
        encoding="utf-8"
    )
    for marker in (
        "scripts/qualify_released_consumers.py",
        "GitHub's `sha256:<hex>` release-asset digest",
        "pds_core.provider_diagnostics",
        "One consumer failure does not erase evidence for the others.",
        "The qualification runner accepts an explicit Core wheel and never rebuilds it.",
        "Core v0.6.3",
        "pds-paper-data-suite#44",
    ):
        assert marker in document


def test_ci_has_isolated_released_consumer_qualification_job() -> None:
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )
    assert "released-consumer-compatibility:" in workflow
    assert "scripts/build_v062_provisional_candidate.py" not in workflow
    assert "python -m build --wheel" in workflow
    assert "scripts/qualify_released_consumers.py" in workflow
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert "actions/upload-artifact@v4" in workflow
