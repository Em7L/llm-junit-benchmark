from __future__ import annotations

"""Filesystem helpers for writing artifacts, staging repositories, and snapshotting source trees."""

import json
import shutil
from pathlib import Path
from typing import Iterable, Sequence
from uuid import uuid4

from benchmark_pipeline.models import FileArtifact


def safe_rel_path(raw_path: str) -> Path:
    normalized = raw_path.replace("\\", "/").strip()
    if normalized.startswith("/"):
        raise ValueError(f"Unsafe relative path: {raw_path!r}")
    candidate = Path(normalized)
    if not normalized or candidate.is_absolute() or candidate.drive:
        raise ValueError(f"Unsafe relative path: {raw_path!r}")

    normalized = normalized.strip("/")
    candidate = Path(normalized)
    if not normalized or candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        raise ValueError(f"Unsafe relative path: {raw_path!r}")
    return candidate


def write_artifacts(root: Path, files: Sequence[FileArtifact]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for artifact in files:
        target = root / safe_rel_path(artifact.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(artifact.content, encoding="utf-8")


def reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def repo_snapshot(
    root: Path,
    *,
    include_extensions: Iterable[str] | None = None,
    ignore_dirs: Iterable[str] = ("target", ".git", ".idea", ".vscode", "__pycache__"),
) -> str:
    include_set = {ext.lower() for ext in include_extensions or []}
    ignore_set = set(ignore_dirs)
    chunks: list[str] = []

    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if any(part in ignore_set for part in path.parts):
            continue
        if include_set and path.suffix.lower() not in include_set and path.name != "pom.xml":
            continue
        rel = path.relative_to(root).as_posix()
        content = path.read_text(encoding="utf-8")
        chunks.append(f"FILE: {rel}\n```\n{content}\n```")

    return "\n\n".join(chunks)


def tree_listing(root: Path, ignore_dirs: Iterable[str] = ("target", ".git")) -> str:
    ignore_set = set(ignore_dirs)
    lines: list[str] = []
    for path in sorted(root.rglob("*")):
        if any(part in ignore_set for part in path.parts):
            continue
        rel = path.relative_to(root)
        suffix = "/" if path.is_dir() else ""
        lines.append(rel.as_posix() + suffix)
    return "\n".join(lines)


def copy_tree_into(source_root: Path, destination_root: Path) -> None:
    for path in sorted(source_root.rglob("*")):
        rel = path.relative_to(source_root)
        target = destination_root / rel
        if path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)


def directories_match(left_root: Path, right_root: Path) -> bool:
    if not left_root.exists() or not right_root.exists():
        return False

    left_files = sorted(path.relative_to(left_root).as_posix() for path in left_root.rglob("*") if path.is_file())
    right_files = sorted(path.relative_to(right_root).as_posix() for path in right_root.rglob("*") if path.is_file())
    if left_files != right_files:
        return False

    for rel in left_files:
        if (left_root / rel).read_text(encoding="utf-8") != (right_root / rel).read_text(encoding="utf-8"):
            return False
    return True


def stage_repo_with_tests(repo_root: Path, tests_root: Path) -> Path:
    staging_root = repo_root.parent / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    temp_dir = staging_root / f"agent-eval-{uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    copy_tree_into(repo_root, temp_dir)
    copy_tree_into(tests_root, temp_dir)
    return temp_dir


def stage_repo_with_artifacts(repo_root: Path, files: Sequence[FileArtifact]) -> Path:
    staging_root = repo_root.parent / ".staging"
    staging_root.mkdir(parents=True, exist_ok=True)
    temp_dir = staging_root / f"agent-eval-{uuid4().hex[:8]}"
    temp_dir.mkdir(parents=True, exist_ok=False)
    copy_tree_into(repo_root, temp_dir)
    write_artifacts(temp_dir, files)
    return temp_dir


def dump_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
