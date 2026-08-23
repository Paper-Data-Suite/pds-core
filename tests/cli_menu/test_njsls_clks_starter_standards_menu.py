"""Interactive menu coverage for the 2020 NJSLS-CLKS starter pack."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.standards import load_standards_library
from tests.cli_menu.conftest import library_file, run_menu


def test_menu_can_select_and_install_clks_as_second_sorted_pack(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, err = run_menu(
        tmp_path,
        monkeypatch,
        capsys,
        "5\n4\n2\nYES\n\n5\n6\n",
    )

    assert code == 0
    assert "Choose a starter standards pack:" in out
    assert (
        "2. 2020 NJSLS Career Readiness, Life Literacies and Key Skills "
        "Starter Standards"
    ) in out
    assert "Pack ID: njsls_clks_2020" in out
    assert "Framework IDs: njsls_clks_2020" in out
    assert "Installed starter standards pack: njsls_clks_2020" in out
    assert err == ""
    assert library_file(tmp_path).is_file()

    library = load_standards_library(library_file(tmp_path))
    assert len(library.standards) == 301
    assert len(library.profiles) == 4
    assert len(library.frameworks) == 1
    assert not (tmp_path / "standards" / "usage").exists()
