from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict

TP_30m = timedelta(minutes=30)
TP_1h = timedelta(hours=1)
TP_1D = timedelta(days=1)
TP_2D = timedelta(days=2)
TP_1W = timedelta(days=7)
TP_1M = timedelta(days=30)
TP_1Y = timedelta(days=365)

_SECONDS_IN_DAY = 60 * 60 * 24
_SECONDS_IN_WEEK = 7 * _SECONDS_IN_DAY


def format_timestamp(time: datetime) -> str:
    return time.isoformat()


def is_tz_aware(dt: datetime) -> bool:
    # Following https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None


def require_tz_aware_datetime(dt: datetime) -> None:
    if not is_tz_aware(dt):
        raise ValueError(f"datetime {dt} must be time zone aware.")


def format_time_as_delta(time: datetime) -> str:
    return format_time_delta(time - datetime.now(timezone.utc))


def format_time_delta(delta: timedelta) -> str:
    if -TP_1D < delta < TP_1D:
        return "Today"
    if TP_1D < delta < TP_2D:
        return "Tomorrow"
    if TP_1D < -delta < TP_2D:
        return "Yesterday"
    if TP_2D < delta < TP_1W:
        return "This Week"
    if TP_2D < -delta < TP_1W:
        return "Past Week"
    if delta > TP_1W:
        # Future
        return "The future"
    elif -delta > TP_1W:
        # past
        answer = list()
        remainder = -delta
        if remainder > TP_1Y:
            years = remainder // TP_1Y
            answer.append(f"{years} year" + ("s" if years > 1 else ""))
            remainder = remainder % TP_1Y
        if remainder > TP_1M:
            months = remainder // TP_1M
            answer.append(f"{months} month" + ("s" if months > 1 else ""))
            remainder = remainder % TP_1M
        if remainder > TP_1D and -delta // TP_1Y < 1:
            days = remainder // TP_1D
            answer.append(f"{days} day" + ("s" if days > 1 else ""))
        answer.append("ago")

    return " ".join(answer)


class TimePeriod(BaseModel):
    model_config = ConfigDict(frozen=True)
    start: datetime
    length: timedelta

    @classmethod
    def for_range(cls, start: datetime, end: datetime):
        return cls(start=start, length=(end-start))

    @property
    def end(self) -> datetime:
        return self.start + self.length

    def contains(self, other: datetime):
        if not isinstance(other, datetime):
            raise ValueError(f"Cannot check TimePeriod contains {repr(other)}")
        return self.start < other < self.end

    def overlaps(self, other: 'TimePeriod'):
        return (self.contains(other.start)
                or self.contains(other.end)
                or other.contains(self.start)
                or other.contains(self.end)
                or self.start == other.start)

    def shift(self, delta: timedelta):
        return TimePeriod(start=self.start + delta, length=self.length)

    def combine(self, other: 'TimePeriod') -> 'TimePeriod':
        start = min(self.start, other.start)
        end = max(self.end, other.end)
        length = end - start
        return type(self)(start=start,
                          length=length)


def format_time_weekday_and_time(dt: datetime) -> str:
    delta = datetime.now(timezone.utc) - dt

    weeks_ago = int(delta.total_seconds() // _SECONDS_IN_WEEK)

    abbrev_weekday = dt.strftime("%a")

    return "{week} {weekday} {time}".format(
        week="last" if weeks_ago == 0 else f"{weeks_ago:2d} weeks ago",
        weekday=abbrev_weekday,
        time=format_time(dt))


def format_time(dt):
    time = "{hour:>2d}:{minute} {ampm}".format(
        hour=int(dt.strftime("%I")),
        minute=dt.strftime("%M"),
        ampm=dt.strftime("%p"))
    return time


def format_time_period_weekday_and_time(period: TimePeriod) -> str:
    if period.length > timedelta(days=1):
        raise ValueError("Cannot format time period longer than one day")

    formatted_start = format_time_weekday_and_time(period.start)
    formatted_end = format_time(period.end)
    return f"{formatted_start} — {formatted_end}"

def now() -> datetime:
    return datetime.now(timezone.utc)

def days_ago(days: int) -> datetime:
    return now() - timedelta(days=days)