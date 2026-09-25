from datetime import datetime
from zoneinfo import ZoneInfo

LAGOS = ZoneInfo("Africa/Lagos")

# Demo clock. These are evaluation inputs, not the machine clock.
# Friday for the seeded promise is 2026-09-25 in Africa/Lagos.
BEFORE_DUE = datetime(2026, 9, 24, 9, 0, tzinfo=LAGOS)
AFTER_DUE = datetime(2026, 9, 26, 9, 0, tzinfo=LAGOS)
