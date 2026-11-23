"""Tests of layout files: reading, matching parts and locations, writing (plain Python)."""

import json
import pathlib

import pytest

from inventree_virtual_bins import layout as L

PARTS = [
    {'pk': 1, 'ipn': 'EL-301', 'name': 'Main board'},
    {'pk': 2, 'ipn': 'EL-302', 'name': 'Radio module'},
    {'pk': 3, 'ipn': '', 'name': 'Screw M3'},
    {'pk': 4, 'ipn': 'DUP-1', 'name': 'Finished unit'},
    {'pk': 5, 'ipn': 'DUP-1', 'name': 'Test unit'},
    {'pk': 6, 'ipn': '', 'name': 'Washer'},
    {'pk': 7, 'ipn': '', 'name': 'Washer'},
    {'pk': 8, 'ipn': 'Washer', 'name': 'Something else'},
]

PLACES = [
    {'pk': 10, 'path': 'Factory/Bench'},
    {'pk': 11, 'path': 'Factory/Bench/Tray'},
    {'pk': 12, 'path': 'Stores/Shelf A/A1'},
    {'pk': 13, 'path': 'Factory/Bench/Tray/Inner'},
]


def ref(**values):
    return {'pk': None, 'ipn': '', 'name': '', 'text': '', **values}


# References


@pytest.mark.parametrize('value, expected', [
    (None, None), ('', None), ({}, None), ('   ', None), ({'name': ''}, None),
    (5, ref(pk=5)), ('5', ref(text='5')), ('  EL-301 ', ref(text='EL-301')),
    ({'pk': 5}, ref(pk=5)), ({'id': '5'}, ref(pk=5)),
    ({'ipn': 'A', 'name': ' B  c '}, ref(ipn='A', name='B c')),
    ({'IPN': 'A'}, ref(ipn='A')),
    ({'pk': 3, 'ipn': 'A', 'name': 'B', 'other': 1}, ref(pk=3, ipn='A', name='B')),
])
def test_part_ref(value, expected):
    assert L.part_ref(value) == expected


@pytest.mark.parametrize('value', [True, -1, 1.5, 0, [1], {'pk': 'abc'}, {'pk': -2}])
def test_part_ref_refuses(value):
    with pytest.raises(L.LayoutError):
        L.part_ref(value)


@pytest.mark.parametrize('value, expected', [
    (None, None), ('', None), ({}, None),
    (7, {'pk': 7, 'path': ''}), ('./A1', {'pk': None, 'path': './A1'}),
    ({'path': 'Stores/A', 'pk': 3}, {'pk': 3, 'path': 'Stores/A'}),
    ({'path': ''}, None),
])
def test_location_ref(value, expected):
    assert L.location_ref(value) == expected


@pytest.mark.parametrize('value', [False, -3, 2.5, ['x'], {'pk': 'x'}])
def test_location_ref_refuses(value):
    with pytest.raises(L.LayoutError):
        L.location_ref(value)


@pytest.mark.parametrize('reference, text', [
    (ref(name='Radio', ipn='EL-302', pk=2), 'Radio (EL-302)'),
    (ref(ipn='EL-302'), 'EL-302'),
    (ref(text='Radio'), 'Radio'),
    (ref(pk=9), 'number 9'),
    ({'pk': 4, 'path': './A1'}, './A1'),
    ({'pk': 4, 'path': ''}, 'number 4'),
    (None, ''),
])
def test_describe_ref(reference, text):
    assert L.describe_ref(reference) == text


# Matching parts


@pytest.mark.parametrize('reference, expected', [
    # A number on its own
    (ref(pk=2), 2),
    # A number which agrees with the IPN or the name
    (ref(pk=2, ipn='el-302'), 2),
    (ref(pk=2, name='RADIO MODULE'), 2),
    (ref(pk=2, ipn='wrong', name='Radio module'), 2),
    # A number which belongs to another part: the IPN and name decide
    (ref(pk=2, ipn='EL-301', name='Main board'), 1),
    (ref(pk=99, ipn='EL-301'), 1),
    # IPN, name or both
    (ref(ipn='EL-301'), 1),
    (ref(name='screw m3'), 3),
    (ref(ipn='EL-301', name='Main board'), 1),
    # The IPN decides when the name has changed since the file was made
    (ref(ipn='EL-301', name='Old name of the board'), 1),
    # Two parts with one IPN: the name tells them apart
    (ref(ipn='DUP-1', name='Test unit'), 5),
    (ref(ipn='DUP-1', name='Finished unit'), 4),
    # ... or the number does
    (ref(pk=5, ipn='DUP-1'), 5),
    (ref(pk=7, name='Washer'), 7),
    # A bare text: the IPN first, then the name
    (ref(text='EL-302'), 2),
    (ref(text='radio module'), 2),
    (ref(text='Washer'), 8),
])
def test_match_part(reference, expected):
    assert L.match_part(reference, PARTS) == (expected, '')


@pytest.mark.parametrize('reference, why', [
    (ref(pk=99), 'there is no part with that number'),
    (ref(ipn='NOPE'), 'no such part'),
    (ref(name='Nothing like it'), 'no such part'),
    (ref(text='Nothing like it'), 'no such part'),
    (ref(ipn='DUP-1'), '2 parts match'),
    (ref(name='Washer'), '2 parts match'),
    (ref(pk=1, name='Washer'), '2 parts match'),
    # The number is right somewhere else, but here it is another part
    (ref(pk=2, ipn='EL-999', name='Gearbox'), 'no such part (number 2 is "Radio module" here)'),
    (ref(pk=2, text='Gearbox'), 'no such part (number 2 is "Radio module" here)'),
    (ref(ipn='EL-301', name='Radio module', pk=None), None),
])
def test_match_part_fails(reference, why):
    pk, reason = L.match_part(reference, PARTS)

    if why is None:
        # An IPN and a name which point at two different parts: the IPN decides
        assert pk == 1
    else:
        assert pk is None and reason == why


def test_match_part_with_nothing_to_choose_from():
    assert L.match_part(ref(name='Radio module'), []) == (None, 'no such part')
    assert L.match_part(ref(pk=2), []) == (None, 'there is no part with that number')


# Matching locations


@pytest.mark.parametrize('reference, expected', [
    ({'pk': 11, 'path': ''}, 11),
    ({'pk': 11, 'path': './Tray'}, 11),
    ({'pk': None, 'path': './Tray'}, 11),
    ({'pk': None, 'path': './tray/inner'}, 13),
    ({'pk': None, 'path': '.'}, 10),
    ({'pk': None, 'path': 'stores/shelf a/a1'}, 12),
    ({'pk': None, 'path': '/Stores/Shelf A/A1/'}, 12),
    # A number which is another location here: the path decides
    ({'pk': 12, 'path': './Tray'}, 11),
    ({'pk': 99, 'path': 'Factory/Bench/Tray'}, 11),
])
def test_match_location(reference, expected):
    assert L.match_location(reference, PLACES, 'Factory/Bench') == (expected, '')


@pytest.mark.parametrize('reference, why', [
    ({'pk': 99, 'path': ''}, 'there is no location with that number'),
    ({'pk': None, 'path': './Nope'}, 'no such location'),
    ({'pk': 11, 'path': './Nope'}, 'no such location'),
    ({'pk': None, 'path': 'Tray'}, 'no such location'),
])
def test_match_location_fails(reference, why):
    assert L.match_location(reference, PLACES, 'Factory/Bench') == (None, why)


def test_match_location_two_with_one_path():
    twins = [{'pk': 1, 'path': 'A/B'}, {'pk': 2, 'path': 'A/B'}]

    assert L.match_location({'pk': None, 'path': 'A/B'}, twins, 'A') == (None, '2 locations match')
    assert L.match_location({'pk': 2, 'path': 'A/B'}, twins, 'A') == (2, '')


@pytest.mark.parametrize('path, unit, full', [
    ('./A1', 'Stores/Shelf A', 'Stores/Shelf A/A1'),
    ('./A1/x/', 'Stores/Shelf A', 'Stores/Shelf A/A1/x'),
    ('.', 'Stores/Shelf A', 'Stores/Shelf A'),
    ('./', 'Stores/Shelf A', 'Stores/Shelf A'),
    ('Other/Place', 'Stores/Shelf A', 'Other/Place'),
    (' /Other/Place/ ', 'Stores/Shelf A', 'Other/Place'),
])
def test_absolute_path(path, unit, full):
    assert L.absolute_path(path, unit) == full


@pytest.mark.parametrize('path, unit, written', [
    ('Stores/Shelf A/A1', 'Stores/Shelf A', './A1'),
    ('Stores/Shelf A/A1/x', 'Stores/Shelf A', './A1/x'),
    ('Stores/Shelf A', 'Stores/Shelf A', '.'),
    ('Stores/Shelf AB/A1', 'Stores/Shelf A', 'Stores/Shelf AB/A1'),
    ('Other/Place', 'Stores/Shelf A', 'Other/Place'),
])
def test_relative_path(path, unit, written):
    assert L.relative_path(path, unit) == written
    assert L.absolute_path(written, unit) == path


# Reading a file


def test_parse_a_file_written_by_hand():
    parsed = L.parse_layout_file({
        'kind': 'shelving',
        'product': 'OSN-100',
        'name': 'Shelf',
        'rows': [
            {'name': ' Top ', 'columns': [
                [{'part': 'EL-301', 'size': 'm', 'min': 5, 'max': '20'}, {'label': 'Spare'}],
                {'part': {'ipn': 'EL-302'}, 'location': './A2'},
                [],
            ]},
            [[{'part': 4, 'note': 'n', 'unknown': 'ignored'}]],
        ],
    })

    assert parsed['kind'] == 'shelving' and parsed['name'] == 'Shelf'
    assert parsed['product'] == ref(text='OSN-100')
    assert [row['name'] for row in parsed['rows']] == ['Top', '']
    assert [len(column) for column in parsed['rows'][0]['columns']] == [2, 1]

    first, spare = parsed['rows'][0]['columns'][0]
    assert first == {'id': None, 'label': '', 'part': ref(text='EL-301'), 'location': None,
                     'size': 'm', 'min': 5.0, 'max': 20.0, 'note': ''}
    assert spare['label'] == 'Spare' and spare['part'] is None and spare['size'] == 's'

    single = parsed['rows'][0]['columns'][1][0]
    assert single['part'] == ref(ipn='EL-302') and single['location'] == {'pk': None, 'path': './A2'}

    assert parsed['rows'][1]['columns'][0][0]['part'] == ref(pk=4)
    assert len(L.file_bins(parsed)) == 4


def test_parse_a_layout_as_the_api_stores_it():
    stored = L.clean_layout({'kind': 'bench', 'product': 9, 'rows': [{'name': 'A', 'columns': [
        {'bins': [{'id': 'keep', 'part': 3, 'location': 8, 'size': 'l', 'min': 1, 'max': 2}]},
    ]}]})
    parsed = L.parse_layout_file(stored)

    item = L.file_bins(parsed)[0]
    assert item['id'] == 'keep' and item['part'] == ref(pk=3)
    assert item['location'] == {'pk': 8, 'path': ''} and item['size'] == 'l'
    assert parsed['product'] == ref(pk=9)


@pytest.mark.parametrize('doc, message', [
    (None, 'must be a JSON object'),
    ([], 'must be a JSON object'),
    ({'format': 'something-else', 'rows': []}, 'not a Virtual Bins layout file'),
    ({'version': 2, 'rows': []}, 'newer version'),
    ({'version': 'one', 'rows': []}, 'version'),
    ({}, 'no "rows"'),
    ({'rows': 'x'}, 'no "rows"'),
    ({'kind': 'tower', 'rows': []}, '"kind"'),
    ({'product': [1], 'rows': []}, 'Product'),
    ({'rows': ['x']}, 'Row 1 must be an object'),
    ({'rows': [{'columns': 'x'}]}, 'Row 1: "columns" must be a list'),
    ({'rows': [{'columns': ['x']}]}, 'Row 1, column 1 must be a list of bins'),
    ({'rows': [{'columns': [['x']]}]}, 'Row 1, column 1 must be an object'),
    ({'rows': [{'columns': [[{}, 'x']]}]}, 'Row 1, column 1, bin 2 must be an object'),
    ({'rows': [{'columns': [[{'size': 'xl'}]]}]}, 'Row 1, column 1: "size"'),
    ({'rows': [{'columns': [[{}], [{'min': -1}]]}]}, 'Row 1, column 2: "min"'),
    ({'rows': [{'columns': [[{'max': 'lots'}]]}]}, '"max" must be a number'),
    ({'rows': [{'columns': [[{'min': 9, 'max': 3}]]}]}, '"max" cannot be below "min"'),
    ({'rows': [{}, {'columns': [[{}, {'part': [1]}]]}]}, 'Row 2, column 1, bin 2: A part must be'),
    ({'rows': [{'columns': [[{'location': True}]]}]}, 'A location must be'),
    ({'rows': [{'columns': [[{}] * 9]}]}, 'stack can have at most 8'),
    ({'rows': [{'columns': [[{}]] * 41}]}, 'at most 40 columns'),
    ({'rows': [{}] * 13}, 'at most 12 rows'),
    ({'rows': [{'columns': [[{}] * 8] * 40}] * 2}, 'at most 400 bins'),
])
def test_parse_refuses(doc, message):
    with pytest.raises(L.LayoutError, match=message):
        L.parse_layout_file(doc)


def test_parse_accepts_the_current_format_and_version():
    parsed = L.parse_layout_file({'format': L.FILE_FORMAT, 'version': L.FILE_VERSION, 'rows': []})
    assert parsed == {'name': '', 'kind': 'bench', 'product': None, 'rows': []}


def test_wanted_lists_everything_to_look_up():
    parsed = L.parse_layout_file({'product': {'ipn': 'P-1', 'pk': 50}, 'rows': [{'columns': [
        [{'part': 4}, {'part': 'Radio Module', 'location': 7}],
        [{'part': {'ipn': 'EL-1', 'name': 'Main Board', 'pk': 9}, 'location': './A1'}],
        [{'label': 'Spare'}],
    ]}]})

    assert L.wanted(parsed) == {
        'part_pks': {4, 9, 50},
        'part_texts': {'radio module', 'el-1', 'main board', 'p-1'},
        'location_pks': {7},
        'location_paths': {'./A1'},
    }


# Writing a file


def exported():
    layout = L.clean_layout({'kind': 'shelving', 'product': 9, 'rows': [
        {'name': 'Left bay', 'columns': [
            {'bins': [{'part': 1, 'size': 'm', 'min': 10, 'max': 30}]},
            {'bins': [{'part': 2, 'min': 2.5}, {'location': 7, 'label': 'Mixed', 'note': 'Keep "dry"'}]},
            {'bins': [{'label': 'Spare'}]},
            {'bins': [{'part': 3, 'location': 8}]},
        ]},
        {'name': '', 'columns': []},
    ]})
    doc = L.export_layout(
        layout,
        name='Bench 1',
        parts={1: {'ipn': 'EL-1', 'name': 'Board'}, 2: {'ipn': '', 'name': 'Radio'},
               9: {'ipn': 'P-9', 'name': 'Node'}},
        locations={7: {'path': 'Factory/Bench 1/Tray'}, 8: {'path': 'Stores/Bulk'}},
        unit_path='Factory/Bench 1',
    )

    return layout, doc


def test_export_names_parts_and_locations():
    _layout, doc = exported()

    assert doc['format'] == L.FILE_FORMAT and doc['version'] == L.FILE_VERSION
    assert doc['name'] == 'Bench 1' and doc['kind'] == 'shelving'
    assert doc['product'] == {'ipn': 'P-9', 'name': 'Node', 'pk': 9}

    columns = doc['rows'][0]['columns']
    assert columns[0] == [{'part': {'ipn': 'EL-1', 'name': 'Board', 'pk': 1}, 'size': 'm', 'min': 10, 'max': 30}]
    assert columns[1][0] == {'part': {'name': 'Radio', 'pk': 2}, 'size': 's', 'min': 2.5}
    assert columns[1][1] == {'label': 'Mixed', 'location': {'path': './Tray', 'pk': 7}, 'size': 's',
                             'note': 'Keep "dry"'}
    assert columns[2] == [{'label': 'Spare', 'size': 's'}]
    # A part which is not known by name is written with its number only
    assert columns[3] == [{'part': {'pk': 3}, 'location': {'path': 'Stores/Bulk', 'pk': 8}, 'size': 's'}]
    assert doc['rows'][1] == {'name': '', 'columns': []}


def test_export_whole_numbers_are_written_without_a_decimal_point():
    _layout, doc = exported()
    text = L.format_layout_file(doc)

    assert '"min": 10, "max": 30' in text and '"min": 2.5' in text
    assert '10.0' not in text


def test_file_text_is_json_with_one_bin_on_a_line():
    _layout, doc = exported()
    text = L.format_layout_file(doc)

    assert json.loads(text) == doc
    assert text.endswith('}\n')

    lines = text.splitlines()
    assert '        [{"part": {"ipn": "EL-1", "name": "Board", "pk": 1}, "size": "m", "min": 10, "max": 30}],' in lines
    assert '          {"part": {"name": "Radio", "pk": 2}, "size": "s", "min": 2.5},' in lines
    assert sum(1 for line in lines if '"size"' in line) == 5
    assert all(line.count('"size"') <= 1 for line in lines)


def test_file_text_keeps_other_alphabets_readable():
    doc = L.export_layout(
        L.clean_layout({'rows': [{'name': 'Regał', 'columns': [{'bins': [{'label': 'Śruby'}]}]}]}),
        name='Stół', parts={}, locations={}, unit_path='',
    )
    text = L.format_layout_file(doc)

    assert 'Śruby' in text and 'Regał' in text and json.loads(text) == doc


def test_a_file_without_rows_or_bins_is_still_json():
    doc = L.export_layout(L.empty_layout(), name='X', parts={}, locations={}, unit_path='X')
    assert json.loads(L.format_layout_file(doc))['rows'] == [{'name': '', 'columns': []}]


def test_round_trip_through_a_file():
    layout, doc = exported()
    parsed = L.parse_layout_file(json.loads(L.format_layout_file(doc)))

    parts = [{'pk': 1, 'ipn': 'EL-1', 'name': 'Board'}, {'pk': 2, 'ipn': '', 'name': 'Radio'},
             {'pk': 3, 'ipn': '', 'name': 'Other'}, {'pk': 9, 'ipn': 'P-9', 'name': 'Node'}]
    places = [{'pk': 7, 'path': 'Factory/Bench 1/Tray'}, {'pk': 8, 'path': 'Stores/Bulk'}]

    before = [(item['part'], item['location'], item['label'], item['size'], item['min'], item['max'],
               item['note']) for item in L.all_bins(layout)]
    after = []

    for item in L.file_bins(parsed):
        part = L.match_part(item['part'], parts)[0] if item['part'] else None
        place = L.match_location(item['location'], places, 'Factory/Bench 1')[0] if item['location'] else None
        after.append((part, place, item['label'], item['size'], item['min'], item['max'], item['note']))

    assert after == before
    assert L.match_part(parsed['product'], parts) == (9, '')


def test_round_trip_into_another_unit_and_another_inventree():
    """The same file, where every number is different and the unit has another name."""
    _layout, doc = exported()
    parsed = L.parse_layout_file(json.loads(L.format_layout_file(doc)))

    parts = [{'pk': 101, 'ipn': 'EL-1', 'name': 'Board'}, {'pk': 102, 'ipn': '', 'name': 'Radio'},
             {'pk': 1, 'ipn': 'ZZ', 'name': 'A different part with an old number'}]
    places = [{'pk': 70, 'path': 'Plant 2/Bench 9/Tray'}, {'pk': 7, 'path': 'Plant 2/Unrelated'}]

    bins = L.file_bins(parsed)
    assert L.match_part(bins[0]['part'], parts) == (101, '')
    assert L.match_part(bins[1]['part'], parts) == (102, '')
    # Below the unit: found below the new unit. Elsewhere: not there in this InvenTree.
    assert L.match_location(bins[2]['location'], places, 'Plant 2/Bench 9') == (70, '')
    assert L.match_location(bins[4]['location'], places, 'Plant 2/Bench 9') == (None, 'no such location')
    # Written with a number only: not trusted to be the same part elsewhere... but it is all there is
    assert L.match_part(bins[4]['part'], parts) == (None, 'there is no part with that number')


# Keeping ids


def test_reuse_ids_for_bins_which_show_the_same_thing():
    old = L.clean_layout({'rows': [{'columns': [
        {'bins': [{'id': 'a', 'part': 1}, {'id': 'b', 'part': 2, 'location': 5}]},
        {'bins': [{'id': 'c', 'label': 'Spare'}, {'id': 'd', 'part': 1}]},
    ]}]})
    new = L.clean_layout({'rows': [{'columns': [
        {'bins': [{'id': 'x1', 'part': 2, 'location': 5}]},
        {'bins': [{'id': 'x2', 'part': 1}, {'id': 'x3', 'part': 1}, {'id': 'x4', 'part': 1}]},
        {'bins': [{'id': 'x5', 'part': 9}, {'id': 'a', 'part': 8}, {'id': 'x6', 'label': 'Spare'}]},
    ]}]})

    result = L.reuse_ids(new, old)
    ids = [item['id'] for item in L.all_bins(result)]

    # Same part and location: the old id, in the order the old bins were laid out
    assert ids[0] == 'b' and ids[1] == 'a' and ids[2] == 'd' and ids[6] == 'c'
    # A third bin of part 1 has no old bin to take over, and a new part neither
    assert ids[3] == 'x4' and ids[4] == 'x5'
    # An id which was handed to another bin is not used twice
    assert ids[5] != 'a' and len(set(ids)) == len(ids)


def test_reuse_ids_without_a_previous_layout():
    new = L.clean_layout({'rows': [{'columns': [{'bins': [{'id': 'x', 'part': 1}]}]}]})
    assert L.reuse_ids(new, None) is new and L.all_bins(new)[0]['id'] == 'x'


# The files in examples/


@pytest.mark.parametrize('name, kind, bins', [('assembly-bench', 'bench', 20), ('shelving-unit', 'shelving', 12)])
def test_the_example_files_are_layout_files(name, kind, bins):
    path = pathlib.Path(__file__).parent.parent / 'examples' / f'{name}.json'
    text = path.read_text(encoding='utf-8')
    parsed = L.parse_layout_file(json.loads(text))

    assert parsed['kind'] == kind and len(L.file_bins(parsed)) == bins
    # Written the way a download writes them, so that an edited download looks the same
    assert L.format_layout_file(json.loads(text)) == text
    # No numbers of parts or locations: those only mean something in one InvenTree
    assert '"pk"' not in text
