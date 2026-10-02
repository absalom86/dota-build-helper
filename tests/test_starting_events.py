import pytest

from dota_helper.starting_events import purchase_count, starting_event_counts


@pytest.mark.parametrize('key,charges,expected', [
    ('tango', 3, 1), ('tango', 6, 2), ('tango', 9, 3),
    ('enchanted_mango', 2, 2), ('faerie_fire', 2, 2), ('ward_sentry', 2, 2),
    ('magic_wand', 20, 1), ('magic_stick', 10, 1), ('infused_raindrop', 6, 1),
])
def test_synthetic_starting_stacks_count_units_without_multiplying_use_charges(key, charges, expected):
    assert purchase_count({'key': key, 'time': -89, 'charges': charges}) == expected


@pytest.mark.parametrize('charges', [0, -1, True, None, '6', 6.0, 1, 4, 91, 93])
def test_ambiguous_or_malformed_tango_stack_cannot_claim_pack_count(charges):
    assert purchase_count({'key': 'tango', 'time': -89, 'charges': charges}) is None


def test_charge_multiplier_applies_only_to_negative_time_inventory_records():
    assert purchase_count({'key': 'tango', 'time': 0, 'charges': 6}) == 1
    assert purchase_count({'key': 'ward_sentry', 'time': 30, 'charges': 2}) == 1
    assert purchase_count({'key': 'tango', 'time': -89}) == 1


def test_repeated_packs_and_stacked_packs_are_both_preserved():
    events = [{'key': 'tango', 'time': -89, 'charges': 6},
              {'key': 'tango', 'time': -30},
              {'key': 'branches', 'time': -89}, {'key': 'branches', 'time': -89},
              {'key': 'branches', 'time': 0}]
    assert starting_event_counts(events) == {'tango': 3, 'branches': 2}


@pytest.mark.parametrize('events', [None, [], [{}], [{'key': 'tango', 'time': float('nan')}],
                                  [{'key': 'tango', 'time': -89, 'charges': 4}],
                                  [{'key': 'unknown', 'time': -89}],
                                  [{'key': 'branches', 'time': 0}]])
def test_unusable_log_is_not_returned_as_zero_or_partial_counts(events):
    assert starting_event_counts(events) is None
