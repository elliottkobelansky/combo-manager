"""Slot generation: which nights have shows, how many sets each. Pure function of Settings."""
from datetime import timedelta
from typing import List

from .model import Night, Settings


def generate_nights(s: Settings) -> List[Night]:
    by_weekday = {sd.weekday: sd for sd in s.show_days}
    nights = {}
    d = s.start_date
    while d <= s.end_date:
        sd = by_weekday.get(d.weekday())
        if sd and d not in s.skip_dates:
            nights[d] = Night(d, sd.venue, sd.slots, sd.first_set, sd.set_length, sd.break_minutes,
                              sd.supervision_preferred)
        d += timedelta(days=1)
    preferred_venues = {sd.venue.casefold() for sd in s.show_days if sd.supervision_preferred}
    for d, venue, n in s.extra_dates:            # an extra date is preferred when its venue is
        nights[d] = Night(d, venue, n, *s.extra_times.get(d, (None, 0, 0)), venue.casefold() in preferred_venues)
    return [nights[d] for d in sorted(nights)]
