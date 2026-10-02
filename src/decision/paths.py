"""Filesystem locations for a decision workspace."""

import os
from pathlib import Path


def home() -> Path:
    override = os.environ.get("DECISION_HOME")
    if override:
        return Path(override)
    return Path.cwd() / ".decision"
