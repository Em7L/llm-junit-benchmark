from __future__ import annotations

import shutil
import unittest
from pathlib import Path

import _path  # noqa: F401

from benchmark_pipeline.evaluation.test_cleaning import disable_baseline_failing_tests


class TestTestCleaning(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("run_outputs/.unit-tests/test-cleaning")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_disables_failing_method_and_adds_import(self) -> None:
        test_file = self.root / "src/test/java/com/example/AppTest.java"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "\n".join(
                [
                    "package com.example;",
                    "",
                    "import org.junit.jupiter.api.Test;",
                    "",
                    "class AppTest {",
                    "    @Test",
                    "    void failsOnBaseline() {",
                    '        throw new RuntimeException("bad");',
                    "    }",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        disabled = disable_baseline_failing_tests(
            self.root,
            ["com.example.AppTest#failsOnBaseline"],
        )

        text = test_file.read_text(encoding="utf-8")
        self.assertEqual(disabled, ["com.example.AppTest#failsOnBaseline"])
        self.assertIn("import org.junit.jupiter.api.Disabled;", text)
        self.assertIn('@Disabled("Excluded because it fails on the baseline")', text)
        self.assertIn("@Test\n    @Disabled", text)

    def test_normalizes_parameterized_surefire_method_names(self) -> None:
        test_file = self.root / "src/test/java/com/example/AppTest.java"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "\n".join(
                [
                    "package com.example;",
                    "",
                    "import org.junit.jupiter.api.*;",
                    "",
                    "class AppTest {",
                    "    @Test",
                    "    void rejectsInvalidBudget() {",
                    "    }",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        disabled = disable_baseline_failing_tests(
            self.root,
            ["com.example.AppTest#rejectsInvalidBudget()[1]"],
        )

        text = test_file.read_text(encoding="utf-8")
        self.assertEqual(disabled, ["com.example.AppTest#rejectsInvalidBudget"])
        self.assertNotIn("import org.junit.jupiter.api.Disabled;", text)
        self.assertIn('@Disabled("Excluded because it fails on the baseline")', text)

    def test_raises_when_failing_method_cannot_be_found(self) -> None:
        test_file = self.root / "src/test/java/com/example/AppTest.java"
        test_file.parent.mkdir(parents=True)
        test_file.write_text(
            "\n".join(
                [
                    "package com.example;",
                    "",
                    "import org.junit.jupiter.api.Test;",
                    "",
                    "class AppTest {",
                    "    @Test",
                    "    void existingTest() {",
                    "    }",
                    "}",
                    "",
                ]
            ),
            encoding="utf-8",
        )

        with self.assertRaises(RuntimeError):
            disable_baseline_failing_tests(self.root, ["com.example.AppTest#missingTest"])


if __name__ == "__main__":
    unittest.main()
