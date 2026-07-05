"""Default model profile IDs for runtime entry points."""

from __future__ import annotations

import os


DEFAULT_DIRECTOR_PROFILE_ID = "deepseek-v4-flash-director"
DEFAULT_WRITER_PROFILE_ID = "deepseek-v4-pro-writer"
FAKE_DIRECTOR_PROFILE_ID = "fake-director"
FAKE_WRITER_PROFILE_ID = "fake-writer"


def profile_ids_from_env() -> tuple[str, str]:
    director_profile_id = (
        os.environ.get("AWP_DIRECTOR_PROFILE_ID", "").strip()
        or DEFAULT_DIRECTOR_PROFILE_ID
    )
    writer_profile_id = (
        os.environ.get("AWP_WRITER_PROFILE_ID", "").strip()
        or DEFAULT_WRITER_PROFILE_ID
    )
    return director_profile_id, writer_profile_id
