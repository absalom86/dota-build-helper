"""Match averages only: never convert a medal or leaderboard place into MMR."""
import math
import re


MEDALS = ('', 'Herald', 'Guardian', 'Crusader', 'Archon', 'Legend', 'Ancient', 'Divine', 'Immortal')


def rank_tier(value, average=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        return None
    if value == 80 or (10 <= value < 80 and (average or value % 10 in range(6))):
        return value
    return None


def average_rank_value(route):
    """Read only a supplied match average, including older OpenDota records."""
    value = rank_tier(route.average_rank, average=True)
    if value is not None:
        return value
    if route.match_rank_source == 'OpenDota match average':
        return rank_tier(route.match_rank, average=True)
    if route.source == 'OpenDota' and route.evidence.startswith('OpenDota sampled pub · 10/10 recorded ranks Immortal'):
        return 80
    return None


def match_rank(route):
    average = average_rank_value(route)
    if average is not None:
        return average
    value = rank_tier(route.match_rank, average=route.match_rank_source == 'OpenDota match average')
    if value is not None:
        return value
    # Older saved searches kept this exact match evidence, but no structured rank.
    # Do not read player-profile medals or leaderboard places as match ratings.
    if route.source == 'STRATZ':
        found = re.match(r'^Match bracket (Immortal|\d+)(?: ·|$)', route.evidence)
        if found:
            return 80 if found[1] == 'Immortal' else rank_tier(int(found[1]))
    if route.source == 'OpenDota' and route.evidence.startswith('OpenDota sampled pub · 10/10 recorded ranks Immortal'):
        return 80
    return None


def rank_name(value):
    if value is None:
        return 'Rank unknown'
    medal, stars = divmod(int(value), 10)
    # A fractional average is not an exact individual medal/star count.
    suffix = f' {stars}' if value == int(value) and 1 <= stars <= 5 and medal < 8 else ''
    return MEDALS[medal] + suffix


def numeric_mmr(value):
    if type(value) in (int, float) and math.isfinite(value) and 0 < value < 30000:
        return int(value)
    return None


def average_mmr_text(route):
    """Cell text for an Average MMR column; pro pubs may still have an average."""
    value = numeric_mmr(route.average_mmr)
    return f'{value:,}' if value is not None and not route.demo and not route.tournament else '—'


def average_mmr_help(route):
    if route.demo:
        return 'Synthetic demo; no real match-average MMR.'
    if route.tournament:
        return 'Tournament match; ranked-pub average MMR does not apply.'
    value = numeric_mmr(route.average_mmr)
    if value is not None:
        source = route.average_mmr_source or f'{route.source} supplied match average'
        return (f'{value:,} match-average MMR · {source}. '
                'This is not the selected player’s individual MMR, and was not calculated from medals or leaderboard places.')
    return ('Numeric match-average MMR was not supplied. '
            'Medals and leaderboard places are not converted into MMR.')


def average_rank_text(route):
    """Cell text separates a supplied average from a broad match bracket."""
    if route.demo or route.tournament:
        return '—'
    average = average_rank_value(route)
    if average is not None:
        return rank_name(average)
    bracket = match_rank(route)
    return rank_name(bracket) + ' (bracket)' if bracket is not None else '—'


def average_rank_help(route):
    if route.demo:
        return 'Synthetic demo; no real match-average rank.'
    if route.tournament:
        return 'Tournament match; ranked-pub average rank does not apply.'
    average = average_rank_value(route)
    if average is not None:
        source = (route.average_rank_source or
                  (route.match_rank_source if route.match_rank_source == 'OpenDota match average' else '') or
                  f'{route.source} supplied match-average rank')
        return (f'{rank_name(average)} · average rank tier {average:g} · {source}. '
                'This is a match rank average, not numeric MMR or the selected player’s medal.')
    bracket = match_rank(route)
    if bracket is not None:
        source = route.match_rank_source or f'{route.source} saved match evidence'
        return (f'{rank_name(bracket)} · {source}. Match-average rank was not supplied; '
                'the bracket shown is a fallback, not an exact match average. '
                'An individual player’s profile rank is never substituted.')
    return ('Neither a match-average rank nor a match bracket was supplied. '
            'An individual player’s medal or leaderboard place is not a match average.')


def rating_text(route):
    if route.demo:
        return 'DEMO'
    if route.tournament or route.pro_player:
        return 'PRO'
    mmr = numeric_mmr(route.average_mmr)
    if mmr:
        return f'{mmr:,} MMR'
    rank = match_rank(route)
    suffix = ' (avg)' if rank is not None and rank != 80 and average_rank_value(route) is not None else ''
    return rank_name(rank) + suffix


def rating_help(route):
    if route.demo:
        return 'Synthetic demo; no real match rating.'
    if route.tournament:
        return 'Professional tournament game; a ranked-pub MMR does not apply.'
    if numeric_mmr(route.average_mmr):
        source = route.average_mmr_source or route.source
        return (f'{source} reports a match average of {numeric_mmr(route.average_mmr):,} MMR. '
                'This is not the selected player’s individual MMR.')
    rank = match_rank(route)
    if rank is not None:
        source = route.average_rank_source or route.match_rank_source or f'{route.source} saved match evidence'
        return (f'{rank_name(rank)} · {source}. Numeric MMR unavailable. '
                'Rank brackets sort highest first; equal ranks use newest first. '
                'Immortal games without numeric MMR cannot be distinguished by skill within that bracket.')
    return ('Neither numeric match MMR nor a match rank bracket was supplied. '
            'An individual player’s medal or leaderboard position is not a match rating. Unknown ratings sort last.')
