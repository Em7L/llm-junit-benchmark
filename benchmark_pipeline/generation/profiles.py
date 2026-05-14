from __future__ import annotations

"""Benchmark profile definitions for controlled baseline repository generation."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class BenchmarkProfile:
    profile_id: str
    domain: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


BENCHMARK_DOMAINS: tuple[str, ...] = (
    "library",
    "meal-planning",
    "inventory",
    "billing",
)


BENCHMARK_PROFILES: tuple[BenchmarkProfile, ...] = tuple(
    BenchmarkProfile(profile_id=domain, domain=domain)
    for domain in BENCHMARK_DOMAINS
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
            "Benchmark profile requirements:",
            f"- Profile id: `{profile.profile_id}`.",
            f"- The application domain MUST be: `{profile.domain}`.",
        ]
    )
