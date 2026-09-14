"""Pinned official LIBERO-Plus task selection; no simulation or model imports."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
from pathlib import Path

REPOSITORY = "https://github.com/sylvestf/LIBERO-plus"
REVISION = "4976dc30028e805ff8094b55501d532c48fec182"
ASSETS_REPOSITORY = "Sylvest/LIBERO-plus"
ASSETS_REVISION = "dd2bd61b7d9a6fef1abc52d606e983b41886a149"
ASSETS_SHA256 = "96764a4bfbdaea98d4411598caeab235458318fe0f549611b93d1a323027b3cf"
DEFAULT_BASE = (
    "pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate"
)
SUPPORTED_CATEGORIES = ("Camera Viewpoints", "Light Conditions", "Robot Initial States")
SCHEMA = "robot-reel.libero-plus-plan.v1"


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_catalog(map_text: str, classification_text: str, suite: str) -> list[dict]:
    """Read the upstream literal map without executing its Python module."""
    tree = ast.parse(map_text)
    if (
        len(tree.body) != 1 or not isinstance(tree.body[0], ast.Assign)
        or len(tree.body[0].targets) != 1
        or not isinstance(tree.body[0].targets[0], ast.Name)
        or tree.body[0].targets[0].id != "libero_task_map"
    ):
        raise ValueError("expected the upstream literal libero_task_map assignment")
    mapping = ast.literal_eval(tree.body[0].value)
    classification = json.loads(classification_text)
    names = mapping.get(suite)
    rows = classification.get(suite)
    if not isinstance(names, list) or not isinstance(rows, list):
        raise ValueError("suite is absent from the official map or classification")
    if len(names) != len(rows) or len(set(names)) != len(names):
        raise ValueError("official task map and classification differ")
    checked = []
    for index, (name, row) in enumerate(zip(names, rows, strict=True)):
        if (
            not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_]+", name)
            or not isinstance(row, dict) or type(row.get("id")) is not int
            or row["id"] != index + 1 or row.get("name") != name
            or not isinstance(row.get("category"), str)
            or type(row.get("difficulty_level")) is not int
        ):
            raise ValueError(f"official task identity mismatch at runtime index {index}")
        checked.append({**row, "runtime_index": index})
    return checked


def make_plan(
    repository: Path, *, suite: str = "libero_spatial",
    base_task: str = DEFAULT_BASE,
    categories: tuple[str, ...] = ("Camera Viewpoints", "Light Conditions"),
    difficulty: int = 1, seed: int = 195, max_steps: int = 220,
) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9_]+", base_task):
        raise ValueError("base task must be a portable task name")
    if type(difficulty) is not int or not 1 <= difficulty <= 3:
        raise ValueError("difficulty must be 1, 2 or 3")
    if not categories or len(set(categories)) != len(categories) or any(
        category not in SUPPORTED_CATEGORIES for category in categories
    ):
        raise ValueError("choose distinct supported perturbation categories")
    if type(seed) is not int or not 0 <= seed < 2**32:
        raise ValueError("seed must be an unsigned 32-bit integer")
    if type(max_steps) is not int or not 16 <= max_steps <= 1000:
        raise ValueError("max_steps must be an integer from 16 to 1000")
    repository = repository.resolve()
    actual = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True, timeout=10
    ).strip()
    if actual != REVISION:
        raise ValueError(f"this adapter requires the reviewed LIBERO-Plus revision {REVISION}")
    root = repository / "libero/libero"
    source_paths = (
        root / "benchmark/libero_suite_task_map.py",
        root / "benchmark/task_classification.json",
        root / "envs/env_wrapper.py",
    )
    # Verify tracked source bytes against the pinned tree, not just HEAD's label.
    for path in source_paths:
        original = subprocess.check_output(
            ["git", "show", f"{REVISION}:{path.relative_to(repository).as_posix()}"],
            cwd=repository, timeout=10,
        )
        if path.read_bytes() != original:
            raise ValueError(f"reviewed upstream source changed: {path.name}")
    catalog = read_catalog(source_paths[0].read_text(), source_paths[1].read_text(), suite)
    base_bddl = root / "bddl_files" / suite / f"{base_task}.bddl"
    initial_state = root / "init_files" / suite / f"{base_task}.pruned_init"
    if not base_bddl.is_file() or not initial_state.is_file():
        raise ValueError("base task definition or original initial state is missing")
    conditions = [{
        "name": "baseline", "task_name": base_task, "category": "Original task",
        "official_task_id": None, "runtime_index": None, "difficulty_level": None,
        "bddl_file": base_bddl.relative_to(root).as_posix(),
        "bddl_sha256": digest(base_bddl),
    }]
    for category in categories:
        matches = [
            row for row in catalog
            if row["category"] == category and row["difficulty_level"] == difficulty
            and row["name"].startswith(base_task + "_")
        ]
        if not matches:
            raise ValueError(f"no official {category} task matches this base task and difficulty")
        # Deterministic first official ID, selected before any model outcome.
        row = matches[0]
        native_name = row["name"]
        physical_name = native_name.split("_view_", 1)[0]
        bddl = root / "bddl_files" / suite / f"{physical_name}.bddl"
        if not bddl.is_file():
            raise ValueError(f"official task definition is missing: {physical_name}")
        conditions.append({
            "name": category.lower().replace(" ", "-"),
            "task_name": native_name, "category": category,
            "official_task_id": row["id"], "runtime_index": row["runtime_index"],
            "difficulty_level": row["difficulty_level"],
            "bddl_file": bddl.relative_to(root).as_posix(), "bddl_sha256": digest(bddl),
        })
    return {
        "schema": SCHEMA, "suite": suite, "base_task": base_task,
        "seed": seed, "initial_state_index": 0, "settle_steps": 10,
        "max_steps": max_steps, "conditions": conditions,
        "source": {
            "repository": REPOSITORY, "revision": REVISION,
            "source_files": {
                path.relative_to(repository).as_posix(): digest(path) for path in source_paths
            },
            "assets_repository": ASSETS_REPOSITORY, "assets_revision": ASSETS_REVISION,
            "assets_archive_sha256": ASSETS_SHA256,
            "initial_state_file": initial_state.relative_to(root).as_posix(),
            "initial_state_sha256": digest(initial_state),
        },
        "scope": (
            "Original task plus a preselected official LIBERO-Plus subset. "
            "One episode per condition, not the full 10030-task benchmark. "
            "The upstream environment applies perturbations; rendered pixels are not edited. "
            "Official IDs are one-based and runtime indices are zero-based."
        ),
    }
