from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

import _path  # noqa: F401

from benchmark_pipeline.fs_utils import (
    dump_json,
    repo_snapshot,
    safe_rel_path,
    stage_repo_with_tests,
    tree_listing,
    write_artifacts,
)
from benchmark_pipeline.models import FileArtifact


class TestFsUtils(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("run_outputs/.unit-tests/fs-utils")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_safe_rel_path_accepts_normal_repo_paths(self) -> None:
        self.assertEqual(
            safe_rel_path(r"src\main\java\com\example\App.java").as_posix(),
            "src/main/java/com/example/App.java",
        )

    def test_safe_rel_path_rejects_escape_paths(self) -> None:
        unsafe_paths = [
            "",
            "/tmp/outside.java",
            "../outside.java",
            "src/../../outside.java",
            r"C:\tmp\outside.java",
            "C:drive-relative.java",
        ]

        for raw_path in unsafe_paths:
            with self.subTest(raw_path=raw_path):
                with self.assertRaises(ValueError):
                    safe_rel_path(raw_path)

    def test_write_artifacts_rejects_path_traversal(self) -> None:
        with self.assertRaises(ValueError):
            write_artifacts(
                self.root,
                [FileArtifact(path="../outside.txt", content="nope")],
            )

        self.assertFalse((self.root.parent / "outside.txt").exists())

    def test_stage_repo_with_tests_merges_into_isolated_staging_copy(self) -> None:
        repo = self.root / "repo"
        tests = self.root / "tests"
        (repo / "src/main/java/com/example").mkdir(parents=True)
        (tests / "src/test/java/com/example").mkdir(parents=True)
        (repo / "pom.xml").write_text("<project/>", encoding="utf-8")
        (repo / "src/main/java/com/example/App.java").write_text("class App {}", encoding="utf-8")
        (tests / "src/test/java/com/example/AppTest.java").write_text("class AppTest {}", encoding="utf-8")

        staged = stage_repo_with_tests(repo, tests)

        try:
            self.assertTrue((staged / "pom.xml").exists())
            self.assertTrue((staged / "src/main/java/com/example/App.java").exists())
            self.assertTrue((staged / "src/test/java/com/example/AppTest.java").exists())
            self.assertNotEqual(staged.resolve(), repo.resolve())
        finally:
            if staged.exists():
                shutil.rmtree(staged)

    def test_repo_snapshot_filters_extensions_and_ignores_build_outputs(self) -> None:
        (self.root / "pom.xml").write_text("<project/>", encoding="utf-8")
        (self.root / "README.md").write_text("readme", encoding="utf-8")
        (self.root / "src/main/java").mkdir(parents=True)
        (self.root / "src/main/java/App.java").write_text("class App {}", encoding="utf-8")
        (self.root / "target").mkdir()
        (self.root / "target/Generated.java").write_text("class Generated {}", encoding="utf-8")

        snapshot = repo_snapshot(self.root, include_extensions={".java"})

        self.assertIn("FILE: pom.xml", snapshot)
        self.assertIn("FILE: src/main/java/App.java", snapshot)
        self.assertNotIn("README.md", snapshot)
        self.assertNotIn("Generated.java", snapshot)

    def test_tree_listing_marks_directories_and_ignores_target(self) -> None:
        (self.root / "src/main/java").mkdir(parents=True)
        (self.root / "src/main/java/App.java").write_text("class App {}", encoding="utf-8")
        (self.root / "target").mkdir()
        (self.root / "target/ignored.txt").write_text("ignored", encoding="utf-8")

        listing = tree_listing(self.root)

        self.assertIn("src/", listing)
        self.assertIn("src/main/java/App.java", listing)
        self.assertNotIn("target", listing)

    def test_dump_json_creates_parent_directory(self) -> None:
        target = self.root / "nested/report.json"
        dump_json(target, {"ok": True})

        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})


if __name__ == "__main__":
    unittest.main()
