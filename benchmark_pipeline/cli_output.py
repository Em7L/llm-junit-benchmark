from __future__ import annotations

"""Small helpers for concise, consistent CLI output."""

from pathlib import Path


def relpath(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def heading(prefix: str, title: str) -> None:
    print()
    print(f"{prefix} {title}")


def kv(prefix: str, label: str, value: object) -> None:
    print(f"{prefix} {label}: {value}")
