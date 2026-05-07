# SPDX-License-Identifier: AGPL-3.0-only
# Copyright (c) 2025-2026 ViralMint Contributors
"""Shared video utility functions — used across multiple services."""
import subprocess
from pathlib import Path


def probe_duration(file_path: Path | str, default: float = 0.0) -> float:
    """Get media file duration in seconds using ffprobe.

    Returns *default* if the probe fails for any reason (missing file,
    corrupt media, ffprobe not installed, etc.).
    """
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(file_path),
            ],
            capture_output=True,
            text=True,
            timeout=15,
        )
        return float(result.stdout.strip())
    except Exception:
        return default
