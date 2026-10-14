"""What the API remembers about each analysis (in memory only, for now)."""

from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, Field


class Status(str, Enum):
    QUEUED = "queued"        # accepted, waiting for a free slot
    ALIGNING = "aligning"    # step 1 Job exists
    CALLING = "calling"      # step 1 succeeded, step 2 Job exists
    SUCCEEDED = "succeeded"
    FAILED = "failed"


RUNNING = (Status.ALIGNING, Status.CALLING)


def now() -> datetime:
    return datetime.now(timezone.utc)


class StepInfo(BaseModel):
    """Where a step runs: filled in by the orchestrator from the cluster."""
    pod: str | None = None
    node: str | None = None
    phase: str | None = None  # Pending / Running / Succeeded / Failed


class Analysis(BaseModel):
    id: str
    status: Status = Status.QUEUED
    created_at: datetime = Field(default_factory=now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    align: StepInfo = Field(default_factory=StepInfo)
    call: StepInfo = Field(default_factory=StepInfo)
    result: dict | None = None  # summary of step 2, read from its last log line
    error: str | None = None
