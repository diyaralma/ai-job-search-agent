"""Etkin kaynakların listesi."""

from __future__ import annotations

from .aggregators import AdzunaSource, JoobleSource
from .ats import ATSSource
from .base import JobSource
from .remote_boards import (
    ArbeitnowSource,
    HimalayasSource,
    JobicySource,
    RemoteOKSource,
    RemotiveSource,
)

ALL_SOURCES: list[JobSource] = [
    RemotiveSource(),
    ArbeitnowSource(),
    RemoteOKSource(),
    JobicySource(),
    HimalayasSource(),
    ATSSource(),
    AdzunaSource(),
    JoobleSource(),
]


def enabled_sources() -> list[JobSource]:
    return [s for s in ALL_SOURCES if s.enabled]
