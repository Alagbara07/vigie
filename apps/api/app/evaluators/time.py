"""Evaluation clock.

Timestamps are stored as timezone-aware instants (PostgreSQL timestamptz).
Comparisons never call datetime.now(). The caller supplies reference_time.

Instant rules, including the unanswered-request threshold, compare those
instants directly. A DATE commitment is different: due_at is the start of the
promised local day, so the commitment is missed only when reference_time falls
on a later calendar date in the business timezone. For the MVP that timezone
is Africa/Lagos, taken from the business row.

At the due instant itself, and for the rest of a DATE due day, the commitment
stays pending. The seeded Friday promise (due 2026-09-25T00:00:00+01:00) is
therefore still pending at 2026-09-25T23:59:00+01:00 and missed at
2026-09-26T00:00:00+01:00.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from app.domain.enums import DuePrecision


def is_past_due(
    due_at: datetime | None,
    due_precision: str | None,
    reference_time: datetime,
    timezone_name: str,
) -> bool:
    if due_at is None:
        return False
    zone = ZoneInfo(timezone_name)
    local_due = due_at.astimezone(zone)
    local_reference = reference_time.astimezone(zone)
    if due_precision == DuePrecision.DATE.value:
        return local_reference.date() > local_due.date()
    return local_reference > local_due
