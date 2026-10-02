"""Small overlay views of the selected route; source purchase logs stay intact."""
from .catalog import clock_text


def near_term_purchases(purchases, second, until):
    """Return lane purchases from one minute ago through two minutes ahead.

    Unknown or pregame clocks use the opening two minutes. ``until`` is the
    existing exclusive section deadline in game seconds, not a new data cutoff.
    Repeated purchases remain separate events so the display can group quantities.
    """
    now = max(0, second if second is not None else 0)
    start = max(0, now - 60)
    end = min(until, now + 120)
    visible = [purchase for purchase in purchases
               if start <= purchase.time <= end and purchase.time < until]
    return visible, f'{clock_text(start)}–{clock_text(end)}'
