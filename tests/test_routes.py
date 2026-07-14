"""Tests for deterministic module-qualified workspace paths."""

from __future__ import annotations

from pathlib import Path

import pytest

from pds_core.identifiers import IdentifierValidationError
from pds_core.routes import (
    ModuleWorkPathError,
    class_dir,
    class_metadata_path,
    class_module_dir,
    class_modules_dir,
    class_roster_path,
    classes_dir,
    module_routes_dir,
    module_work_collection_dir,
    module_work_dir,
    route_registration_path,
    safe_module_work_descendant,
)
from pds_core.routing_models import (
    PDS2_SCHEMA,
    ModuleWorkRef,
    RouteLocator,
    RoutingModelError,
)


def make_work(module_id: str = "concord") -> ModuleWorkRef:
    return ModuleWorkRef(module_id, "english10_p3", "socratic_seminar_1")


def make_locator() -> RouteLocator:
    return RouteLocator(
        PDS2_SCHEMA,
        make_work(),
        "rt_0123456789abcdef0123456789abcdef",
    )


@pytest.mark.parametrize("root", ["paper_data", Path("paper_data")])
def test_class_level_paths_accept_string_and_path_roots(root: str | Path) -> None:
    expected = Path("paper_data") / "classes" / "english10_p3"
    assert classes_dir(root) == Path("paper_data") / "classes"
    assert class_dir(root, "english10_p3") == expected
    assert class_roster_path(root, "english10_p3") == expected / "roster.csv"
    assert class_metadata_path(root, "english10_p3") == expected / "class.json"


def test_module_qualified_paths_have_exact_layout() -> None:
    root = Path("paper_data")
    work = make_work()
    module_root = root / "classes" / "english10_p3" / "modules" / "concord"
    work_root = module_root / "work" / "socratic_seminar_1"

    assert class_modules_dir(root, work.class_id) == module_root.parent
    assert class_module_dir(root, work.class_id, work.module_id) == module_root
    assert module_work_collection_dir(
        root, work.class_id, work.module_id
    ) == module_root / "work"
    assert module_work_dir(root, work) == work_root
    assert module_routes_dir(root, work) == work_root / "routes"
    assert route_registration_path(root, make_locator()) == (
        work_root / "routes" / "rt_0123456789abcdef0123456789abcdef.json"
    )


def test_same_work_id_is_distinct_across_modules() -> None:
    roots = {
        module_work_dir(
            "paper_data",
            ModuleWorkRef(module_id, "english10_p3", "project_check"),
        )
        for module_id in ("scoreform", "quillan", "concord")
    }
    assert len(roots) == 3
    assert all("assignments" not in path.parts for path in roots)


@pytest.mark.parametrize(
    "class_id",
    ["", "English 10", "../english10_p3", "classes/english10_p3", " bad"],
)
def test_paths_reject_invalid_class_ids(class_id: str) -> None:
    with pytest.raises(IdentifierValidationError, match="class_id"):
        class_modules_dir("paper_data", class_id)


@pytest.mark.parametrize(
    "module_id",
    ["", "Concord", "con cord", "../concord", "pds/concord", "concord|x"],
)
def test_direct_module_paths_reject_invalid_or_mixed_case_ids(
    module_id: str,
) -> None:
    with pytest.raises(IdentifierValidationError, match="module_id"):
        class_module_dir("paper_data", "english10_p3", module_id)


@pytest.mark.parametrize(
    "value",
    [
        {"module_id": "concord", "class_id": "english10_p3", "work_id": "w"},
        ("concord", "english10_p3", "w"),
        "concord/english10_p3/w",
        object(),
    ],
)
def test_work_paths_require_actual_module_work_ref(value: object) -> None:
    with pytest.raises(RoutingModelError, match="ModuleWorkRef"):
        module_work_dir("paper_data", value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "value",
    [
        {"schema": "PDS2"},
        ("PDS2", "concord"),
        "PDS2|m=concord",
        object(),
    ],
)
def test_registration_path_requires_actual_route_locator(value: object) -> None:
    with pytest.raises(RoutingModelError, match="RouteLocator"):
        route_registration_path("paper_data", value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "relative_path",
    [
        "activity.json",
        Path("pages/page_1.json"),
        "artifacts/artifact_1/pages/page_1.json",
        "attachments/source notes.pdf",
        ".hidden/module-state.json",
    ],
)
def test_safe_module_work_descendant_accepts_module_owned_paths(
    relative_path: str | Path,
) -> None:
    expected_parts = str(relative_path).replace("\\", "/").split("/")
    assert safe_module_work_descendant(
        "paper_data", make_work(), relative_path
    ) == module_work_dir("paper_data", make_work()).joinpath(*expected_parts)


@pytest.mark.parametrize(
    "relative_path",
    [
        "",
        ".",
        "..",
        "../outside.json",
        "pages/../../outside.json",
        "pages/./page_1.json",
        "/absolute/path.json",
        r"\absolute\path.json",
        r"C:\absolute\path.json",
        r"C:relative-drive-path.json",
        r"\\server\share\path.json",
        "pages//page_1.json",
        r"pages\\page_1.json",
        "pages/",
        " pages/page_1.json",
        "pages/page_1.json ",
        "pages/\x00bad.json",
        r"pages\..\outside.json",
        "pages/..\\outside.json",
    ],
)
def test_safe_module_work_descendant_rejects_unsafe_paths(
    relative_path: str,
) -> None:
    with pytest.raises(ModuleWorkPathError):
        safe_module_work_descendant("paper_data", make_work(), relative_path)


def test_path_helpers_do_not_mutate_filesystem(tmp_path: Path) -> None:
    root = tmp_path / "missing"
    work = make_work()
    locator = make_locator()

    paths = [
        classes_dir(root),
        class_dir(root, work.class_id),
        class_roster_path(root, work.class_id),
        class_metadata_path(root, work.class_id),
        class_modules_dir(root, work.class_id),
        class_module_dir(root, work.class_id, work.module_id),
        module_work_collection_dir(root, work.class_id, work.module_id),
        module_work_dir(root, work),
        module_routes_dir(root, work),
        route_registration_path(root, locator),
        safe_module_work_descendant(root, work, "pages/page_1.json"),
    ]

    assert all(not path.exists() for path in paths)
    assert not root.exists()
