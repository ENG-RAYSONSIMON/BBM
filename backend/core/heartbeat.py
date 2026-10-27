"""Liveness for the scheduler: a job that finishes cleanly touches a file,
and the container's healthcheck fails once that file is too old."""

from pathlib import Path

from django.conf import settings


def beat():
    path = settings.SCHEDULER_HEARTBEAT_FILE
    if path:
        Path(path).touch()
