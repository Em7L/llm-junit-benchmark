from __future__ import annotations

"""Benchmark profile definitions for controlled baseline repository generation."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BenchmarkProfile:
    profile_id: str
    complexity: str
    min_classes: int
    max_classes: int
    min_loc: int
    max_loc: int
    min_public_methods: int
    max_public_methods: int
    min_complex_methods: int
    min_cyclomatic_complexity: int
    min_cross_class_workflows: int

    def to_dict(self) -> dict[str, str | int]:
        return asdict(self)


BENCHMARK_PROFILES: tuple[BenchmarkProfile, ...] = (
    BenchmarkProfile(
        profile_id="low",
        complexity="low",
        min_classes=4,
        max_classes=5,
        min_loc=150,
        max_loc=250,
        min_public_methods=8,
        max_public_methods=12,
        min_complex_methods=2,
        min_cyclomatic_complexity=3,
        min_cross_class_workflows=1,
    ),
    BenchmarkProfile(
        profile_id="high",
        complexity="high",
        min_classes=8,
        max_classes=10,
        min_loc=500,
        max_loc=800,
        min_public_methods=20,
        max_public_methods=30,
        min_complex_methods=5,
        min_cyclomatic_complexity=5,
        min_cross_class_workflows=3,
    ),
)

BENCHMARK_PROFILE_IDS: tuple[str, ...] = tuple(profile.profile_id for profile in BENCHMARK_PROFILES)
BENCHMARK_PROFILES_BY_ID: dict[str, BenchmarkProfile] = {
    profile.profile_id: profile for profile in BENCHMARK_PROFILES
}


def get_benchmark_profile(profile_id: str) -> BenchmarkProfile:
    try:
        return BENCHMARK_PROFILES_BY_ID[profile_id]
    except KeyError as exc:
        raise ValueError(f"Unknown benchmark profile: {profile_id}") from exc


def render_benchmark_profile_prompt(profile: BenchmarkProfile) -> str:
    return "\n".join(
        [
            "Complexity requirements:",
            f"- Requested complexity level: `{profile.complexity}`.",
            f"- Use {profile.min_classes}-{profile.max_classes} production classes.",
            f"- Keep total production LOC (excluding blanks/comments) around {profile.min_loc}-{profile.max_loc}.",
            f"- Include around {profile.min_public_methods}-{profile.max_public_methods} public methods across the codebase.",
            (
                f"- Include at least {profile.min_complex_methods} methods with several decision points "
                f"(roughly cyclomatic complexity >= {profile.min_cyclomatic_complexity}), such as nested `if/else`, "
                "`switch`, or loop-and-condition combinations."
            ),
            (
                f"- Include at least {profile.min_cross_class_workflows} cross-class workflows where one service or "
                "orchestrator coordinates behavior across multiple other classes."
            ),
            "- Choose a self-contained business-logic-oriented application domain; do not add external services or frameworks.",
        ]
    )
