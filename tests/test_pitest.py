from __future__ import annotations

import shutil
import unittest
from pathlib import Path

import _path  # noqa: F401

from benchmark_pipeline.tools.pitest import calculate_mutation_score, parse_pitest_mutations


class TestPitestParsing(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path("run_outputs/.unit-tests/pitest")
        if self.root.exists():
            shutil.rmtree(self.root)
        self.root.mkdir(parents=True)

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_calculates_mutation_score_from_scored_statuses(self) -> None:
        score = calculate_mutation_score(
            {
                "KILLED": 3,
                "SURVIVED": 1,
                "NO_COVERAGE": 1,
                "TIMED_OUT": 4,
            }
        )

        self.assertEqual(score, 0.6)

    def test_parses_mutations_xml(self) -> None:
        report_file = self.root / "mutations.xml"
        report_file.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<mutations>
  <mutation detected="true" status="KILLED" numberOfTestsRun="2">
    <sourceFile>Calculator.java</sourceFile>
    <mutatedClass>com.example.Calculator</mutatedClass>
    <mutatedMethod>add</mutatedMethod>
    <methodDescription>(II)I</methodDescription>
    <lineNumber>12</lineNumber>
    <mutator>org.pitest.mutationtest.engine.gregor.mutators.MathMutator</mutator>
    <index>4</index>
    <block>0</block>
    <killingTest>com.example.CalculatorTest.adds()</killingTest>
    <description>Replaced integer addition with subtraction</description>
  </mutation>
</mutations>
""",
            encoding="utf-8",
        )

        mutations = parse_pitest_mutations(report_file)

        self.assertEqual(len(mutations), 1)
        mutation = mutations[0]
        self.assertTrue(mutation.detected)
        self.assertEqual(mutation.status, "KILLED")
        self.assertEqual(mutation.number_of_tests_run, 2)
        self.assertEqual(mutation.mutated_class, "com.example.Calculator")
        self.assertEqual(mutation.line_number, 12)
        self.assertIn("com.example.Calculator|add|(II)I|12|", mutation.mutant_id)
        self.assertEqual(mutation.index, 4)
        self.assertEqual(mutation.block, 0)

    def test_parses_nested_pitest_indexes_and_blocks(self) -> None:
        report_file = self.root / "nested-mutations.xml"
        report_file.write_text(
            """<?xml version="1.0" encoding="UTF-8"?>
<mutations>
  <mutation detected="false" status="NO_COVERAGE" numberOfTestsRun="0">
    <sourceFile>DiscountPolicy.java</sourceFile>
    <mutatedClass>com.example.DiscountPolicy</mutatedClass>
    <mutatedMethod>discountFor</mutatedMethod>
    <methodDescription>()V</methodDescription>
    <lineNumber>15</lineNumber>
    <mutator>org.pitest.mutationtest.engine.gregor.mutators.ConditionalsBoundaryMutator</mutator>
    <indexes><index>31</index></indexes>
    <blocks><block>8</block></blocks>
    <killingTest/>
    <description>changed conditional boundary</description>
  </mutation>
</mutations>
""",
            encoding="utf-8",
        )

        mutation = parse_pitest_mutations(report_file)[0]

        self.assertEqual(mutation.index, 31)
        self.assertEqual(mutation.block, 8)
        self.assertTrue(mutation.mutant_id.endswith("|31|8"))


if __name__ == "__main__":
    unittest.main()
