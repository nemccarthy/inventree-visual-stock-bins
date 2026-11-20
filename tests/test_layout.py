"""Tests of the layout rules and the bin arithmetic (plain Python, no InvenTree)."""

import pytest

from inventree_virtual_bins import layout as L


def make(rows):
    """Build a layout from lists: rows -> columns -> bins."""
    return L.clean_layout({
        'rows': [
            {'name': name, 'columns': [{'bins': column} for column in columns]}
            for name, columns in rows
        ]
    })


# Cleaning a layout


def test_empty_input_gives_one_empty_row():
    for raw in (None, [], 'text', 7, {}):
        layout = L.clean_layout(raw)
        assert layout['version'] == 1
        assert layout['kind'] == 'bench'
        assert layout['product'] is None
        assert len(layout['rows']) == 1
        assert layout['rows'][0]['columns'] == []


def test_bin_defaults():
    layout = make([('', [[{'part': 5}]])])
    item = L.all_bins(layout)[0]

    assert item['part'] == 5
    assert item['location'] is None
    assert item['size'] == 's'
    assert item['min'] is None and item['max'] is None
    assert item['label'] == '' and item['note'] == ''
    assert item['id'].startswith('b')


def test_ids_are_kept_and_made_unique():
    layout = L.clean_layout({'rows': [{'id': 'row-1', 'columns': [
        {'id': 'c', 'bins': [{'id': 'same'}, {'id': 'same'}, {'id': 'bad id!'}, {'id': ''}]},
        {'id': 'c', 'bins': [{'id': 'x' * 40}]},
    ]}]})

    ids = [item['id'] for item in L.all_bins(layout)]
    assert ids[0] == 'same'
    assert len(set(ids)) == 5
    assert all(len(value) <= 24 for value in ids)
    assert layout['rows'][0]['id'] == 'row-1'

    columns = [column['id'] for column in layout['rows'][0]['columns']]
    assert columns[0] == 'c' and columns[1] != 'c'


def test_cleaning_twice_changes_nothing():
    layout = make([('Left', [[{'part': 1, 'min': 2, 'max': 9}], [{'location': 4}, {}]])])
    assert L.clean_layout(layout) == layout


def test_tolerant_cleaning_drops_what_it_cannot_read():
    layout = L.clean_layout({
        'kind': 'tower',
        'product': 'abc',
        'rows': [
            'not a row',
            {'name': 'A' * 100, 'columns': [
                'not a column',
                {'bins': 'nope'},
                {'bins': ['not a bin', {'part': -3, 'size': 'xl', 'min': 'many', 'max': -1}]},
            ]},
        ],
    })

    assert layout['kind'] == 'bench'
    assert layout['product'] is None
    assert len(layout['rows']) == 1
    assert len(layout['rows'][0]['name']) == L.MAX_NAME

    bins = L.all_bins(layout)
    assert len(bins) == 1
    assert bins[0]['part'] is None and bins[0]['size'] == 's'
    assert bins[0]['min'] is None and bins[0]['max'] is None


def test_columns_without_bins_are_dropped():
    layout = make([('', [[], [{'part': 1}], []])])
    assert len(layout['rows'][0]['columns']) == 1


def test_text_is_trimmed():
    layout = make([('  Left   bay ', [[{'label': '  a\n b  ', 'note': 'n' * 500}]])])
    item = L.all_bins(layout)[0]

    assert layout['rows'][0]['name'] == 'Left bay'
    assert item['label'] == 'a b'
    assert len(item['note']) == L.MAX_NOTE


def test_max_below_min_is_dropped_when_tolerant():
    item = L.all_bins(make([('', [[{'min': 10, 'max': 5}]])]))[0]
    assert item['min'] == 10 and item['max'] is None


@pytest.mark.parametrize('raw, message', [
    (None, 'must be an object'),
    ({'rows': 'x'}, 'no rows'),
    ({'kind': 'tower', 'rows': []}, 'Kind'),
    ({'product': 'abc', 'rows': []}, 'Product'),
    ({'rows': ['x']}, 'row must be an object'),
    ({'rows': [{'columns': 'x'}]}, 'list of columns'),
    ({'rows': [{'columns': ['x']}]}, 'column must be an object'),
    ({'rows': [{'columns': [{'bins': 'x'}]}]}, 'list of bins'),
    ({'rows': [{'columns': [{'bins': ['x']}]}]}, 'bin must be an object'),
    ({'rows': [{'columns': [{'bins': [{'size': 'xl'}]}]}]}, 'size'),
    ({'rows': [{'columns': [{'bins': [{'min': -1}]}]}]}, 'levels'),
    ({'rows': [{'columns': [{'bins': [{'max': 'lots'}]}]}]}, 'levels'),
    ({'rows': [{'columns': [{'bins': [{'min': 10, 'max': 5}]}]}]}, 'below its minimum'),
    ({'rows': [{'columns': [{'bins': [{'part': 'abc'}]}]}]}, 'part'),
    ({'rows': [{'columns': [{'bins': [{'location': 1.5}]}]}]}, 'location'),
])
def test_strict_cleaning_refuses(raw, message):
    with pytest.raises(L.LayoutError, match=message):
        L.clean_layout(raw, strict=True)


def test_strict_limits():
    with pytest.raises(L.LayoutError, match='rows'):
        L.clean_layout({'rows': [{'columns': []}] * (L.MAX_ROWS + 1)}, strict=True)

    with pytest.raises(L.LayoutError, match='columns'):
        L.clean_layout(
            {'rows': [{'columns': [{'bins': [{}]}] * (L.MAX_COLUMNS + 1)}]}, strict=True
        )

    with pytest.raises(L.LayoutError, match='stack'):
        L.clean_layout(
            {'rows': [{'columns': [{'bins': [{}] * (L.MAX_STACK + 1)}]}]}, strict=True
        )

    full_row = {'columns': [{'bins': [{}] * L.MAX_STACK}] * L.MAX_COLUMNS}

    with pytest.raises(L.LayoutError, match='bins'):
        L.clean_layout({'rows': [full_row, full_row]}, strict=True)


def test_tolerant_limits():
    full_row = {'columns': [{'bins': [{}] * L.MAX_STACK}] * L.MAX_COLUMNS}
    layout = L.clean_layout({'rows': [full_row] * 20})

    assert len(layout['rows']) <= L.MAX_ROWS
    assert len(L.all_bins(layout)) == L.MAX_BINS


def test_strict_accepts_a_normal_layout():
    layout = L.clean_layout({
        'kind': 'shelving',
        'product': 12,
        'rows': [{'name': 'Shelf 1', 'columns': [
            {'bins': [{'part': 3, 'location': 8, 'size': 'l', 'min': 0, 'max': 40.5, 'label': 'x'}]}
        ]}],
    }, strict=True)

    item = L.all_bins(layout)[0]
    assert layout['kind'] == 'shelving' and layout['product'] == 12
    assert item['part'] == 3 and item['location'] == 8
    assert item['min'] == 0 and item['max'] == 40.5


@pytest.mark.parametrize('value, expected', [
    (None, None), ('', None), (True, None), ('abc', None), (-1, None),
    (float('nan'), None), (float('inf'), None), (1e12, None),
    (0, 0.0), ('12.5', 12.5), (3, 3.0),
])
def test_number(value, expected):
    assert L.number(value) == expected


# Walking a layout


def walk_layout():
    return L.clean_layout({'rows': [
        {'name': 'Left bay', 'columns': [
            {'bins': [{'id': 'a'}]},
            {'bins': [{'id': 'b'}, {'id': 'c'}, {'id': 'd'}]},
        ]},
        {'name': '', 'columns': [{'bins': [{'id': 'e'}, {'id': 'f'}]}]},
    ]})


def test_bins_are_walked_in_reading_order():
    assert [item['id'] for item in L.all_bins(walk_layout())] == list('abcdef')
    assert [(r, c, s) for r, c, s, _ in L.iter_bins(walk_layout())] == [
        (0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 1, 2), (1, 0, 0), (1, 0, 1),
    ]


def test_find_bin():
    layout = walk_layout()
    assert L.find_bin(layout, 'c')['id'] == 'c'
    assert L.find_bin(layout, 'zz') is None


def test_position_in_words():
    layout = walk_layout()

    assert L.bin_position(layout, 'a') == 'Left bay, column 1'
    assert L.bin_position(layout, 'b') == 'Left bay, column 2, top'
    assert L.bin_position(layout, 'c') == 'Left bay, column 2, 2nd from the top'
    assert L.bin_position(layout, 'd') == 'Left bay, column 2, bottom'
    assert L.bin_position(layout, 'e') == 'Row 2, column 1, top'
    assert L.bin_position(layout, 'zz') == ''


def test_position_of_a_single_unnamed_row():
    layout = make([('', [[{'id': 'a'}]])])
    assert L.bin_position(layout, 'a') == 'column 1'


@pytest.mark.parametrize('value, text', [
    (1, '1st'), (2, '2nd'), (3, '3rd'), (4, '4th'), (11, '11th'), (12, '12th'),
    (13, '13th'), (21, '21st'), (22, '22nd'), (103, '103rd'), (111, '111th'),
])
def test_ordinal(value, text):
    assert L.ordinal(value) == text


def test_duplicate_bindings():
    layout = make([('', [
        [{'id': 'a', 'part': 1}], [{'id': 'b', 'part': 1}], [{'id': 'c', 'part': 1, 'location': 4}],
        [{'id': 'd', 'location': 9}], [{'id': 'e', 'location': 9}], [{'id': 'f'}], [{'id': 'g'}],
    ])])

    assert L.duplicate_bindings(layout) == {'a': ['b'], 'b': ['a'], 'd': ['e'], 'e': ['d']}


# Levels


@pytest.mark.parametrize('quantity, low, bound, status', [
    (0, None, True, 'empty'), (0, 10, True, 'empty'), (-1, 10, True, 'empty'),
    (5, 10, True, 'low'), (10, 10, True, 'ok'), (11, 10, True, 'ok'),
    (5, None, True, 'ok'), (5, 0, True, 'ok'),
    (0, 10, False, 'unassigned'), (99, 10, False, 'unassigned'),
])
def test_status(quantity, low, bound, status):
    assert L.bin_status(quantity, low, bound) == status


@pytest.mark.parametrize('quantity, low, high, fill', [
    (0, 10, 40, 0.0), (10, 10, 40, 0.25), (40, 10, 40, 1.0), (80, 10, 40, 1.0),
    (10, 10, None, 0.5), (30, 10, None, 1.0),
    (5, None, None, None), (5, 0, 0, None), (5, None, 20, 0.25),
])
def test_fill(quantity, low, high, fill):
    assert L.fill_fraction(quantity, low, high) == fill


@pytest.mark.parametrize('quantity, low, high, refill', [
    (0, 10, 40, 40), (5, 10, 40, 35), (10, 10, 40, 0), (39, 10, 40, 0),
    (5, 10, None, 5), (0, 10, None, 10), (12, 10, None, 0),
    (0, None, 40, 40), (5, None, 40, 0),
    (0, None, None, 0), (3, None, None, 0),
    (0.5, 1, 2.5, 2.0),
])
def test_refill_quantity(quantity, low, high, refill):
    assert L.refill_quantity(quantity, low, high) == refill


@pytest.mark.parametrize('quantity, per_unit, covers', [
    (10, 1, 10), (10, 4, 2), (3, 4, 0), (0, 1, 0), (10, None, None), (10, 0, None),
    (0.3, 0.1, 3), (1, 0.25, 4), (7.5, 2.5, 3),
])
def test_coverage(quantity, per_unit, covers):
    assert L.coverage(quantity, per_unit) == covers


# Counting and removing


def items(*quantities):
    return [{'pk': index + 1, 'quantity': quantity, 'age': index + 1}
            for index, quantity in enumerate(quantities)]


def as_map(plan):
    return {entry['pk']: entry['quantity'] for entry in plan['set']}


def test_count_of_an_empty_bin_creates_stock():
    assert L.plan_count([], 12) == {'set': [], 'create': 12}
    assert L.plan_count([], 0) == {'set': [], 'create': 0.0}


def test_count_which_matches_lists_every_item_unchanged():
    plan = L.plan_count(items(10, 5), 15)
    assert as_map(plan) == {1: 10, 2: 5}
    assert plan['create'] == 0.0


def test_count_below_takes_from_the_oldest_first():
    assert as_map(L.plan_count(items(10, 5, 8), 20)) == {1: 7, 2: 5, 3: 8}
    assert as_map(L.plan_count(items(10, 5, 8), 6)) == {1: 0, 2: 0, 3: 6}
    assert as_map(L.plan_count(items(10, 5, 8), 0)) == {1: 0, 2: 0, 3: 0}


def test_count_above_adds_to_the_newest():
    assert as_map(L.plan_count(items(10, 5, 8), 30)) == {1: 10, 2: 5, 3: 15}


def test_count_uses_age_not_list_order():
    shuffled = [
        {'pk': 7, 'quantity': 5, 'age': 30},
        {'pk': 8, 'quantity': 5, 'age': 10},
        {'pk': 9, 'quantity': 5, 'age': 20},
    ]

    assert as_map(L.plan_count(shuffled, 12)) == {8: 2, 9: 5, 7: 5}
    assert as_map(L.plan_count(shuffled, 18)) == {8: 5, 9: 5, 7: 8}


def test_count_keeps_the_total_exact_with_fractions():
    plan = L.plan_count(items(0.1, 0.2, 0.3), 0.45)
    assert round(sum(as_map(plan).values()), 6) == 0.45


def test_count_refuses_a_negative():
    with pytest.raises(ValueError):
        L.plan_count(items(5), -1)


def test_remove_takes_oldest_first():
    assert L.plan_remove(items(10, 5, 8), 12) == [
        {'pk': 1, 'quantity': 10}, {'pk': 2, 'quantity': 2},
    ]
    assert L.plan_remove(items(10, 5), 15) == [
        {'pk': 1, 'quantity': 10}, {'pk': 2, 'quantity': 5},
    ]
    assert L.plan_remove(items(0, 5), 3) == [{'pk': 2, 'quantity': 3}]


def test_remove_refuses_too_much_or_nothing():
    with pytest.raises(ValueError, match='does not hold'):
        L.plan_remove(items(10, 5), 16)

    with pytest.raises(ValueError, match='does not hold'):
        L.plan_remove([], 1)

    for quantity in (0, -2):
        with pytest.raises(ValueError, match='more than zero'):
            L.plan_remove(items(10), quantity)


# Bills of materials

NODE, PACK, BOARD, CELL, LEAD, SCREW, GLUE, MANUAL, CASE = range(1, 10)

BOM = {
    NODE: [
        {'part': BOARD, 'quantity': 1},
        {'part': PACK, 'quantity': 1},
        {'part': SCREW, 'quantity': 4},
        {'part': GLUE, 'quantity': 1, 'consumable': True},
        {'part': MANUAL, 'quantity': 1, 'optional': True},
        {'part': CASE, 'quantity': 1},
    ],
    PACK: [
        {'part': CELL, 'quantity': 2},
        {'part': LEAD, 'quantity': 1},
        {'part': SCREW, 'quantity': 2},
        {'part': GLUE, 'quantity': 1, 'consumable': True},
    ],
}


def test_explode_every_level():
    result = L.explode_bom(BOM, NODE)

    assert result['per_unit'] == {BOARD: 1, PACK: 1, SCREW: 6, CELL: 2, LEAD: 1, CASE: 1}
    assert result['consumable'] == {GLUE}
    assert result['loops'] == set()


def test_explode_optional_lines_on_request():
    assert MANUAL not in L.explode_bom(BOM, NODE)['per_unit']
    assert L.explode_bom(BOM, NODE, include_optional=True)['per_unit'][MANUAL] == 1


def test_explode_multiplies_down_the_tree():
    bom = {1: [{'part': 2, 'quantity': 3}], 2: [{'part': 3, 'quantity': 0.5}],
           3: [{'part': 4, 'quantity': 8}]}

    assert L.explode_bom(bom, 1)['per_unit'] == {2: 3, 3: 1.5, 4: 12}


def test_explode_part_used_both_ways_is_not_consumable():
    bom = {1: [{'part': 2, 'quantity': 1, 'consumable': True}, {'part': 2, 'quantity': 2}]}
    result = L.explode_bom(bom, 1)

    assert result['per_unit'] == {2: 2}
    assert result['consumable'] == set()


def test_explode_survives_loops_and_zero_lines():
    bom = {1: [{'part': 2, 'quantity': 1}, {'part': 1, 'quantity': 1}, {'part': 5, 'quantity': 0}],
           2: [{'part': 1, 'quantity': 1}, {'part': 3, 'quantity': 2}]}
    result = L.explode_bom(bom, 1)

    assert result['per_unit'] == {2: 1, 3: 2}
    assert result['loops'] == {1}


def test_explode_of_a_part_without_a_bom():
    assert L.explode_bom({}, 1)['per_unit'] == {}


def test_bom_parts_in_bom_order():
    assert L.bom_parts(BOM, NODE, all_levels=False) == [BOARD, PACK, SCREW, GLUE, MANUAL, CASE]
    assert L.bom_parts(BOM, NODE, all_levels=True) == [
        BOARD, PACK, CELL, LEAD, SCREW, GLUE, MANUAL, CASE,
    ]
    assert L.bom_parts({1: [{'part': 1, 'quantity': 1}]}, 1, all_levels=True) == []


# Units which can be built


def test_buildable_simple_minimum():
    result = L.buildable_units(BOM, NODE, {BOARD: 10, PACK: 7, SCREW: 100, CASE: 9})
    assert result == {'units': 7, 'short': [PACK]}


def test_buildable_uses_built_sub_assemblies_first():
    # 14 packs are 14 units, although there are no leads to build more packs
    stock = {BOARD: 50, PACK: 14, SCREW: 1000, CASE: 50, CELL: 6, LEAD: 0}
    assert L.buildable_units(BOM, NODE, stock) == {'units': 14, 'short': [LEAD]}


def test_buildable_builds_more_sub_assemblies_from_parts():
    stock = {BOARD: 50, PACK: 14, SCREW: 1000, CASE: 50, CELL: 6, LEAD: 10}
    assert L.buildable_units(BOM, NODE, stock) == {'units': 17, 'short': [CELL]}


def test_buildable_shares_a_part_between_levels():
    # 4 screws per node, plus 2 for every pack which still has to be built
    stock = {BOARD: 50, PACK: 2, SCREW: 26, CASE: 50, CELL: 100, LEAD: 100}
    # 5 units: 20 screws + 3 packs x 2 = 26. A sixth needs 32.
    assert L.buildable_units(BOM, NODE, stock) == {'units': 5, 'short': [SCREW]}


def test_buildable_ignores_parts_which_are_not_kept_in_the_unit():
    # Only screws and cases are kept here: boards and packs come from elsewhere
    assert L.buildable_units(BOM, NODE, {SCREW: 40, CASE: 3}) == {'units': 3, 'short': [CASE]}


def test_buildable_cannot_make_a_sub_assembly_with_a_part_missing_from_the_unit():
    # Cells have no bin, so no more packs can be made here: screws do not help
    stock = {BOARD: 50, PACK: 7, SCREW: 1000, CASE: 50, LEAD: 100}
    assert L.buildable_units(BOM, NODE, stock) == {'units': 7, 'short': [PACK]}


def test_buildable_makes_a_sub_assembly_which_has_no_bin():
    # Packs are built and used straight away: only their parts are kept
    stock = {BOARD: 50, SCREW: 1000, CASE: 50, CELL: 9, LEAD: 100}
    assert L.buildable_units(BOM, NODE, stock) == {'units': 4, 'short': [CELL]}


def test_buildable_ignores_consumables_and_optional_lines():
    stock = {BOARD: 5, PACK: 5, SCREW: 100, CASE: 5, GLUE: 0, MANUAL: 0}
    assert L.buildable_units(BOM, NODE, stock)['units'] == 5

    limited = L.buildable_units(BOM, NODE, stock, include_optional=True)
    assert limited == {'units': 0, 'short': [MANUAL]}


def test_buildable_names_every_part_which_runs_out_together():
    result = L.buildable_units(BOM, NODE, {BOARD: 3, PACK: 3, SCREW: 100, CASE: 3})
    assert result == {'units': 3, 'short': sorted([BOARD, PACK, CASE])}


def test_buildable_zero_and_nothing_kept():
    assert L.buildable_units(BOM, NODE, {BOARD: 0, CASE: 5}) == {'units': 0, 'short': [BOARD]}
    assert L.buildable_units(BOM, NODE, {}) is None
    assert L.buildable_units(BOM, NODE, {99: 5}) is None
    assert L.buildable_units({}, NODE, {BOARD: 5}) is None


def test_buildable_does_not_count_stock_of_the_product_itself():
    assert L.buildable_units(BOM, NODE, {NODE: 100, CASE: 2})['units'] == 2


def test_buildable_with_fractional_quantities():
    bom = {1: [{'part': 2, 'quantity': 0.25}]}
    assert L.buildable_units(bom, 1, {2: 1}) == {'units': 4, 'short': [2]}


def test_buildable_large_numbers_and_ceiling():
    bom = {1: [{'part': 2, 'quantity': 1}]}

    assert L.buildable_units(bom, 1, {2: 123456})['units'] == 123456
    assert L.buildable_units(bom, 1, {2: 5e8})['units'] == 1_000_000


def test_buildable_survives_a_loop():
    bom = {1: [{'part': 2, 'quantity': 1}], 2: [{'part': 1, 'quantity': 1}, {'part': 3, 'quantity': 1}]}
    # A BOM which contains itself has no right answer: it only has to end
    assert L.buildable_units(bom, 1, {3: 4, 2: 1})['units'] in (1, 5)
    assert L.buildable_units({1: [{'part': 1, 'quantity': 1}]}, 1, {1: 3})['units'] >= 0


# Generated layouts


def test_layout_from_bins_wraps_into_rows():
    layout = L.layout_from_bins([{'part': n} for n in range(1, 24)], product=7, per_row=10)

    assert layout['product'] == 7
    assert [len(row['columns']) for row in layout['rows']] == [10, 10, 3]
    assert [item['part'] for item in L.all_bins(layout)] == list(range(1, 24))


def test_layout_from_no_bins():
    layout = L.layout_from_bins([])
    assert len(layout['rows']) == 1 and L.all_bins(layout) == []


def test_append_bins_skips_what_is_already_there():
    layout = make([('Left', [[{'id': 'a', 'part': 1}], [{'id': 'b', 'location': 9}],
                             [{'id': 'c', 'part': 5, 'location': 7}]])])
    result = L.append_bins(layout, [
        {'part': 1},                 # the part has a bin
        {'part': 2},                 # new
        {'location': 9},             # the location has a bin
        {'part': 2},                 # just added
        {'part': 1, 'location': 9},  # the location has a bin
        {'part': 5},                 # the part has a bin, in a location of its own
        {'part': 1, 'location': 4},  # a new location, although the part has a bin
        {},                          # nothing to show
    ])

    bins = L.all_bins(result)
    assert [(item['part'], item['location']) for item in bins] == [
        (1, None), (None, 9), (5, 7), (2, None), (1, 4),
    ]
    assert [item['id'] for item in bins[:3]] == ['a', 'b', 'c']
    assert len({item['id'] for item in bins}) == 5
    assert result['rows'][0]['name'] == 'Left'
    assert len(result['rows']) == 2


def test_append_bins_to_an_empty_layout_leaves_no_empty_row():
    result = L.append_bins(L.empty_layout(), [{'part': 1}])
    assert len(result['rows']) == 1 and len(L.all_bins(result)) == 1


def test_summarise():
    assert L.summarise(['ok', 'ok', 'low', 'empty', 'unassigned', 'ok']) == {
        'bins': 6, 'ok': 3, 'low': 1, 'empty': 1, 'unassigned': 1,
    }
