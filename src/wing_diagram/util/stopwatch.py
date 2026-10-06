from datetime import datetime, timedelta

from logging import getLogger

log = getLogger(__name__)


class Stopwatch:

    @classmethod
    def started(cls):
        return cls(datetime.now())

    def __init__(self, start_time: datetime):
        self._start_time = start_time

    def elapsed(self) -> timedelta:
        return datetime.now() - self._start_time
