"""
Failure notifier — publishes download-failure alerts to an AWS SNS topic.

No-op unless SNS_TOPIC_ARN is configured, so the service runs unchanged
on machines without the alert setup.
"""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

import boto3

logger = logging.getLogger("youtube_downloader")

SNS_SUBJECT_MAX_LEN = 100  # hard AWS SNS limit


class SNSNotifier:
    def __init__(
        self,
        topic_arn: Optional[str],
        region: str,
        cooldown_seconds: int = 1800,
        time_fn: Callable[[], float] = time.monotonic,
    ):
        self.topic_arn = topic_arn
        self.cooldown_seconds = cooldown_seconds
        self._time_fn = time_fn
        self._last_sent_at: Optional[float] = None
        self._suppressed_count = 0

        if not topic_arn:
            self._client = None
            logger.warning("SNS_TOPIC_ARN not set - failure email alerts are disabled")
        else:
            self._client = boto3.client(
                "sns",
                region_name=region,
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            )

    def notify(self, youtube_id: str, stage: str, error_detail: str) -> None:
        """Send a failure alert. Never raises - alerting must not break the pipeline."""
        if self._client is None:
            return
        try:
            now = self._time_fn()
            if self._last_sent_at is not None and (now - self._last_sent_at) < self.cooldown_seconds:
                self._suppressed_count += 1
                logger.info(
                    f"[{youtube_id}] Failure alert suppressed by cooldown "
                    f"({self._suppressed_count} suppressed so far)"
                )
                return

            self._client.publish(
                TopicArn=self.topic_arn,
                Subject=self._build_subject(youtube_id, stage),
                Message=self._build_message(youtube_id, stage, error_detail),
            )
            self._last_sent_at = now
            self._suppressed_count = 0
            logger.info(f"[{youtube_id}] Failure alert sent")
        except Exception:
            logger.error(f"[{youtube_id}] Failed to send SNS alert", exc_info=True)

    def _build_subject(self, youtube_id: str, stage: str) -> str:
        subject = f"[Youtube-Downloader] FAILED {youtube_id} ({stage})"
        subject = "".join(c for c in subject if c.isprintable())
        return subject[:SNS_SUBJECT_MAX_LEN - 1]

    def _build_message(self, youtube_id: str, stage: str, error_detail: str) -> str:
        utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        local = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        lines = [
            f"Video:  https://www.youtube.com/watch?v={youtube_id}",
            f"Stage:  {stage}",
            f"Time:   {utc} ({local})",
        ]
        if self._suppressed_count:
            lines.append(
                f"Note:   {self._suppressed_count} earlier failure(s) suppressed during cooldown"
            )
        lines += ["", "Error detail:", error_detail or "(no detail captured)"]
        return "\n".join(lines)
