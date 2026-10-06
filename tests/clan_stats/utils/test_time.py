from datetime import timezone

from wing_diagram.util.time import *


def test_format_time_as_delta():
    earlier = datetime(2000, 1, 20, 10, 0, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    base = datetime(2000, 1, 20, 12, 0, 0, 0, tzinfo=timezone(timedelta(hours=5)))
    later = datetime(2000, 1, 20, 14, 0, 0, 0, tzinfo=timezone(timedelta(hours=5)))

    assert format_time_delta(earlier - base) == "Today"
    assert format_time_delta(later - base) == "Today"

    assert format_time_delta(
        datetime(2000, 1, 21, 14, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "Tomorrow"
    assert format_time_delta(
        datetime(2000, 1, 19, 10, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "Yesterday"

    assert format_time_delta(
        datetime(2000, 1, 22, 14, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "This Week"
    assert format_time_delta(
        datetime(2000, 1, 18, 10, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "Past Week"

    assert format_time_delta(
        datetime(1999, 12, 25, 10, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "26 days ago"

    assert format_time_delta(
        datetime(1999, 10, 18, 10, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "3 months 4 days ago"

    assert format_time_delta(
        datetime(1998, 10, 18, 10, 0, 0, 0, tzinfo=timezone(timedelta(hours=5))) - base) == "1 year 3 months ago"


def test_time_period_overlaps():
    base_time = datetime(2000, 1, 1, 0, 0, 0)

    period1 = TimePeriod(base_time, TP_1h)
    period2 = TimePeriod(base_time + TP_30m, TP_1h)

    assert period1.overlaps(period2)
    assert period2.overlaps(period1)
    assert period1.overlaps(period1)
    assert period2.overlaps(period2)

    period3 = TimePeriod(base_time + TP_1h, TP_1h)

    assert period1.overlaps(period3) is False


def test_time_period_contains():
    base_time = datetime(2000, 1, 1, 0, 0, 0)

    period1 = TimePeriod(base_time, TP_1h)

    assert period1.contains(base_time + TP_30m)
    assert period1.contains(base_time + TP_1h) is False
    assert period1.contains(base_time - TP_30m) is False
