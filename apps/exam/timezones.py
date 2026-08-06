"""
Timezone helpers for the booking flow.

All conversion between a candidate's wall-clock choice and the stored UTC
instant happens here and nowhere else. A candidate who misreads their booking
time misses their exam, and it is unrecoverable.
"""

from datetime import date as date_cls
from datetime import datetime, time, timezone as dt_timezone
from zoneinfo import ZoneInfo

#: One well-known place per UTC offset — a standard picker list, not the full
#: 400+ IANA set. Offsets are computed live so DST stays correct.
STANDARD_TIMEZONES = [
    "Pacific/Pago_Pago",
    "Pacific/Honolulu",
    "America/Anchorage",
    "America/Los_Angeles",
    "America/Denver",
    "America/Chicago",
    "America/New_York",
    "America/Halifax",
    "America/St_Johns",
    "America/Sao_Paulo",
    "Atlantic/South_Georgia",
    "Atlantic/Azores",
    "UTC",
    "Europe/London",
    "Europe/Berlin",
    "Europe/Athens",
    "Europe/Moscow",
    "Asia/Tehran",
    "Asia/Dubai",
    "Asia/Kabul",
    "Asia/Karachi",
    "Asia/Kolkata",
    "Asia/Kathmandu",
    "Asia/Dhaka",
    "Asia/Yangon",
    "Asia/Bangkok",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Darwin",
    "Australia/Sydney",
    "Pacific/Norfolk",
    "Pacific/Auckland",
    "Pacific/Kiritimati",
]

#: Browsers may report legacy names; map them onto the standard list.
TZ_ALIASES = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Asia/Katmandu": "Asia/Kathmandu",
    "Asia/Rangoon": "Asia/Yangon",
}

DEFAULT_TIMEZONE = "Asia/Kolkata"


def canonical(name: str) -> str:
    """Map a browser-reported zone onto our standard name."""
    return TZ_ALIASES.get(name, name)


def is_valid(name: str) -> bool:
    try:
        ZoneInfo(canonical(name))
    except Exception:
        return False
    return True


def offset_minutes(name: str, at: datetime | None = None) -> int:
    at = at or datetime.now(dt_timezone.utc)
    delta = at.astimezone(ZoneInfo(canonical(name))).utcoffset()
    return int(delta.total_seconds() // 60) if delta else 0


def gmt_label(name: str, at: datetime | None = None) -> str:
    """Compact offset shown beside the time field: 'GMT+5:30', 'GMT-4', 'GMT'."""
    minutes = offset_minutes(name, at)
    if minutes == 0:
        return "GMT"

    sign = "+" if minutes > 0 else "-"
    hours, mins = divmod(abs(minutes), 60)
    return f"GMT{sign}{hours}" if mins == 0 else f"GMT{sign}{hours}:{mins:02d}"


def zone_name(name: str) -> str:
    """'America/New_York' -> 'America/New York'."""
    return canonical(name).replace("_", " ")


def timezone_options(include: str | None = None) -> list[dict]:
    """
    Picker options sorted west to east. ``include`` guarantees the candidate's
    own zone is selectable even when it isn't a standard entry.
    """
    at = datetime.now(dt_timezone.utc)
    names = list(STANDARD_TIMEZONES)

    if include:
        include = canonical(include)
        if include not in names and is_valid(include):
            names.append(include)

    options = [
        {
            "value": name,
            "label": gmt_label(name, at),
            "place": zone_name(name),
            "minutes": offset_minutes(name, at),
        }
        for name in names
    ]
    options.sort(key=lambda o: (o["minutes"], o["value"]))
    return options


def compose_utc(day: date_cls, hour: int, minute: int, name: str) -> datetime:
    """
    A wall-clock choice in a timezone becomes the UTC instant we store.

    This is the one conversion in the system that must be right.
    """
    local = datetime.combine(day, time(hour, minute), tzinfo=ZoneInfo(canonical(name)))
    return local.astimezone(dt_timezone.utc)


def to_local(moment: datetime, name: str) -> datetime:
    """A stored UTC instant rendered back in the candidate's timezone."""
    return moment.astimezone(ZoneInfo(canonical(name)))
