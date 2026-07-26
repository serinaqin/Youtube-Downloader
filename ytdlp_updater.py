"""
yt-dlp auto-updater - self-healing for the most common failure cause.

YouTube changes frequently break old yt-dlp versions. When every download
attempt fails, the server asks this module to upgrade yt-dlp and retries
once if a new version was actually installed. A cooldown prevents repeated
upgrade attempts; every outcome surfaces in the alert email.
"""

import subprocess
import time
import logging
from dataclasses import dataclass
from typing import Callable, Optional

logger = logging.getLogger("youtube_downloader")

UPDATE_TIMEOUT_SECONDS = 300


@dataclass
class UpdateResult:
    attempted: bool
    updated: bool = False
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    reason: str = ""

    def summary(self) -> str:
        if self.updated:
            return f"yt-dlp auto-updated {self.old_version} -> {self.new_version}"
        if self.attempted:
            return f"yt-dlp auto-update attempted, not updated ({self.reason})"
        return f"yt-dlp auto-update skipped ({self.reason})"


class YtdlpUpdater:
    def __init__(
        self,
        enabled: bool = True,
        cooldown_seconds: int = 86400,
        time_fn: Callable[[], float] = time.monotonic,
        run_fn: Callable = subprocess.run,
    ):
        self.enabled = enabled
        self.cooldown_seconds = cooldown_seconds
        self._time_fn = time_fn
        self._run_fn = run_fn
        self._last_attempt_at: Optional[float] = None

    def maybe_update(self) -> UpdateResult:
        """Try to upgrade yt-dlp via pip3. Never raises."""
        try:
            if not self.enabled:
                return UpdateResult(attempted=False, reason="disabled")

            now = self._time_fn()
            if self._last_attempt_at is not None and (now - self._last_attempt_at) < self.cooldown_seconds:
                return UpdateResult(attempted=False, reason="cooldown")
            # Set before trying so failed attempts also respect the cooldown.
            self._last_attempt_at = now

            old_version = self._current_version()
            logger.info(f"Attempting yt-dlp auto-update (current: {old_version})...")
            result = self._run_fn(
                ["pip3", "install", "--upgrade", "yt-dlp"],
                capture_output=True,
                text=True,
                timeout=UPDATE_TIMEOUT_SECONDS,
            )
            if result.returncode != 0:
                tail = (result.stderr or "").strip().splitlines()
                reason = f"pip failed: {tail[-1] if tail else 'unknown error'}"
                logger.warning(f"yt-dlp auto-update failed: {reason}")
                return UpdateResult(attempted=True, old_version=old_version, reason=reason)

            new_version = self._current_version()
            if new_version != old_version:
                logger.info(f"yt-dlp auto-updated {old_version} -> {new_version}")
                return UpdateResult(
                    attempted=True, updated=True, old_version=old_version, new_version=new_version
                )
            return UpdateResult(
                attempted=True, old_version=old_version, new_version=new_version, reason="already latest"
            )
        except Exception as e:
            logger.error(f"yt-dlp auto-update error: {e}", exc_info=True)
            return UpdateResult(attempted=True, reason=f"error: {e}")

    def _current_version(self) -> str:
        try:
            r = self._run_fn(["yt-dlp", "--version"], capture_output=True, text=True, timeout=30)
            return r.stdout.strip() or "unknown"
        except Exception:
            return "unknown"
