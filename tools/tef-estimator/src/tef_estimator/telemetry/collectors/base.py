"""Base protocol for telemetry collectors."""

from __future__ import annotations

from typing import Protocol, TypedDict

from tef_estimator.telemetry.db import TelemetryDB


class CollectionSummary(TypedDict, total=False):
    source: str
    status: str
    records_inserted: int
    records_skipped: int
    collection_timestamp: str
    error: str


class Collector(Protocol):
    """Protocol that all collectors implement."""

    SOURCE_ID: str
    CADENCE_DAYS: int

    def collect(self, db: TelemetryDB, **kwargs) -> CollectionSummary: ...
