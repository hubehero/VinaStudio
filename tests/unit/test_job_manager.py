"""The published event must keep the worker's kind, which is what the UI dispatches on.

Adding an envelope ``type`` next to ``**event`` used to be silently overwritten
by the worker payload, so no client ever saw the envelope and live progress went
missing.  These tests pin the published shape.
"""

from __future__ import annotations

from typing import Any

from vinastudio.server.job_manager import JobManager, JobState

JOB_ID = "job-under-test"


class _RecordingHub:
    """Stand-in for EventHub that records what would have been broadcast."""

    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def publish_threadsafe(self, event: dict[str, Any]) -> None:
        self.events.append(event)


def _manager_with_job() -> tuple[JobManager, _RecordingHub]:
    hub = _RecordingHub()
    manager = JobManager()
    manager.bind_hub(hub)
    manager._jobs[JOB_ID] = JobState(job_id=JOB_ID, status="running")
    return manager, hub


def test_progress_event_keeps_the_worker_kind_and_the_job_id() -> None:
    manager, hub = _manager_with_job()

    manager._handle_event(JOB_ID, {"type": "progress", "percent": 42})

    assert len(hub.events) == 1
    event = hub.events[0]
    assert event["type"] == "progress"
    assert event["percent"] == 42
    assert event["jobId"] == JOB_ID


def test_completed_event_keeps_the_kind_and_the_result() -> None:
    manager, hub = _manager_with_job()

    manager._handle_event(JOB_ID, {"type": "completed", "bestAffinity": -9.1, "nPoses": 4})

    event = hub.events[0]
    assert event["type"] == "completed"
    assert event["jobId"] == JOB_ID
    assert event["bestAffinity"] == -9.1


def test_batch_kinds_survive_unchanged() -> None:
    manager, hub = _manager_with_job()

    manager._handle_event(JOB_ID, {"type": "batch_progress", "label": "lig-1", "completed": 0})

    assert hub.events[0]["type"] == "batch_progress"
    assert hub.events[0]["label"] == "lig-1"


def test_unknown_job_publishes_nothing() -> None:
    manager, hub = _manager_with_job()

    manager._handle_event("no-such-job", {"type": "progress", "percent": 1})

    assert hub.events == []
