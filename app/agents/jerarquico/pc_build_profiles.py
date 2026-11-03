"""Compatibility adapter for historical hierarchical imports."""

from app.application.pc_builds import (
    PCBuildProfile,
    choose_pc_build_profile,
    load_pc_build_profiles,
    profiles_for_use,
)

__all__ = [
    "PCBuildProfile",
    "choose_pc_build_profile",
    "load_pc_build_profiles",
    "profiles_for_use",
]
