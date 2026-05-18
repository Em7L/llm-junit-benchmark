from __future__ import annotations

import unittest

import _path  # noqa: F401

from benchmark_pipeline.generation.profiles import (
    BENCHMARK_PROFILE_IDS,
    BENCHMARK_PROFILES,
    BENCHMARK_PROFILES_BY_ID,
    get_benchmark_profile,
    render_benchmark_profile_prompt,
)


class TestProfiles(unittest.TestCase):
    def test_benchmark_profile_registry_contains_expected_complexity_levels(self) -> None:
        self.assertEqual(len(BENCHMARK_PROFILES), 2)
        self.assertEqual(len(BENCHMARK_PROFILE_IDS), 2)
        self.assertEqual(len(BENCHMARK_PROFILES_BY_ID), 2)

    def test_get_benchmark_profile_returns_requested_profile(self) -> None:
        profile = get_benchmark_profile("high")

        self.assertEqual(profile.complexity, "high")
        self.assertEqual(profile.profile_id, "high")
        self.assertEqual(profile.min_classes, 8)
        self.assertEqual(profile.max_classes, 10)

    def test_render_benchmark_profile_prompt_mentions_core_constraints(self) -> None:
        profile = get_benchmark_profile("high")
        prompt = render_benchmark_profile_prompt(profile)

        self.assertIn("Complexity requirements:", prompt)
        self.assertIn("Requested complexity level: `high`.", prompt)
        self.assertIn("Use 8-10 production classes.", prompt)
        self.assertIn("500-800", prompt)


if __name__ == "__main__":
    unittest.main()
