import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.domain.enums import DuePrecision
from app.schemas.analysis import MessageAnalysisProposal, ProposedEvent

WEEKDAYS = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def resolve_weekday(reference_time: datetime, weekday_name: str, timezone_name: str) -> datetime:
    """Return the next occurrence of weekday_name on or after reference_time, in the business timezone."""
    weekday = WEEKDAYS[weekday_name]
    zone = ZoneInfo(timezone_name)
    local = reference_time.astimezone(zone)
    days_ahead = (weekday - local.weekday()) % 7
    target = local.date() + timedelta(days=days_ahead)
    return datetime(target.year, target.month, target.day, tzinfo=zone)


def ground_relative_due_dates(
    proposal: MessageAnalysisProposal,
    reference_time: datetime,
    timezone_name: str,
) -> MessageAnalysisProposal:
    """Resolve a spoken weekday. Ignore any absolute date the model supplied."""
    events = [_ground_event(event, reference_time, timezone_name) for event in proposal.proposed_events]
    return proposal.model_copy(update={"proposed_events": events})


def _ground_event(event: ProposedEvent, reference_time: datetime, timezone_name: str) -> ProposedEvent:
    weekday = _single_weekday(event.due_text)
    if weekday is None:
        if event.due_at is None and event.due_precision is None:
            return event
        return event.model_copy(update={"due_at": None, "due_precision": None})
    return event.model_copy(
        update={
            "due_text": weekday.capitalize(),
            "due_at": resolve_weekday(reference_time, weekday, timezone_name),
            "due_precision": DuePrecision.DATE,
        }
    )


def _single_weekday(due_text: str | None) -> str | None:
    if due_text is None:
        return None
    found = [token for token in re.findall(r"[a-z]+", due_text.lower()) if token in WEEKDAYS]
    if len(found) != 1:
        return None
    return found[0]
