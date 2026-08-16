"""Shared interface and normalization helpers for job sources.

Each source converts what it fetched from its own API into a `JobPosting`. The
only source-specific part is `fetch()`; id generation, HTML cleanup and work-mode
detection are shared here.
"""

from __future__ import annotations

import hashlib
import html
import re
from abc import ABC, abstractmethod
from datetime import datetime, timezone

import httpx

from ..schemas import JobPosting, SearchCriteria, SearchPlan, WorkMode

USER_AGENT = "ai-job-search-agent/0.1 (+https://github.com/local/job-search-automation)"

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")

_REMOTE_HINTS = (
    "remote", "uzaktan", "evden", "work from home", "wfh", "anywhere",
    "distributed", "fully remote", "home office", "telecommute",
)
_HYBRID_HINTS = ("hybrid", "hibrit", "partially remote", "flexible location")
_ONSITE_HINTS = ("on-site", "onsite", "in office", "ofisten", "in-person", "iş yerinde")


def strip_html(raw: str | None) -> str:
    if not raw:
        return ""
    text = _TAG_RE.sub(" ", raw)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def make_id(source: str, external_id: str) -> str:
    digest = hashlib.sha1(f"{source}:{external_id}".encode()).hexdigest()[:16]
    return f"{source}-{digest}"


def detect_work_mode(*texts: str | None) -> WorkMode:
    blob = " ".join(t.lower() for t in texts if t)
    if not blob:
        return "unknown"
    if any(h in blob for h in _HYBRID_HINTS):
        return "hybrid"
    if any(h in blob for h in _REMOTE_HINTS):
        return "remote"
    if any(h in blob for h in _ONSITE_HINTS):
        return "onsite"
    return "unknown"


def parse_date(value) -> datetime | None:
    """Tolerates the various date formats the sources send."""
    if value in (None, "", 0):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d.%m.%Y", "%a, %d %b %Y %H:%M:%S %z"):
            try:
                parsed = datetime.strptime(text, fmt)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


class JobSource(ABC):
    """A single job source."""

    name: str = "base"
    #: Is this an employer's own ATS board? (auto-apply is only possible there)
    ats: str = ""

    @property
    def enabled(self) -> bool:
        return True

    @abstractmethod
    async def fetch(
        self,
        client: httpx.AsyncClient,
        plan: SearchPlan,
        criteria: SearchCriteria,
        limit: int,
    ) -> list[JobPosting]:
        """Fetches postings from the source. May raise; the pipeline catches the
        error and continues with the other sources."""
        raise NotImplementedError
