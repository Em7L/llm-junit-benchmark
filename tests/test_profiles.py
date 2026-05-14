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
    def test_benchmark_profile_registry_contains_expected_domains(self) -> None:
        self.assertEqual(len(BENCHMARK_PROFILES), 4)
        self.assertEqual(len(BENCHMARK_PROFILE_IDS), 4)
        self.assertEqual(len(BENCHMARK_PROFILES_BY_ID), 4)

    def test_get_benchmark_profile_returns_requested_profile(self) -> None:
        profile = get_benchmark_profile("billing")

        self.assertEqual(profile.domain, "billing")
        self.assertEqual(profile.profile_id, "billing")

    def test_render_benchmark_profile_prompt_mentions_core_constraints(self) -> None:
        profile = get_benchmark_profile("library")
        prompt = render_benchmark_profile_prompt(profile)

        self.assertIn("Profile id: `library`.", prompt)
        self.assertIn("The application domain MUST be: `library`.", prompt)


if __name__ == "__main__":
    unittest.main()
