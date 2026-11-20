"""Check the Virtual Bins plugin against a live InvenTree development instance.

Creates its own parts, locations and stock (named with a random suffix), so it
can be run more than once - but only against a throwaway database.

    python dev/integration_check.py http://localhost:8000 <admin token> \
        [--viewer <token>] [--operator <token>] [--nobody <token>]

The three optional tokens belong to the users made by dev/test_users.py, and
turn on the permission checks.

It checks that:

- the quantities the plugin shows match what the InvenTree API reports
- levels, units covered and units which can be built follow the documented rules
- counting, adding, removing, moving and topping up change InvenTree's stock as
  described, and leave the history behind
- a layout is validated, stored beside other metadata, and removed cleanly
- generated layouts, the refill list and "locate" behave as documented
- invalid input and missing permissions are refused
"""

from __future__ import annotations

import argparse
import time
import uuid

import requests

from seed_demo import Api

results = []


def check(name: str, ok, detail=''):
    results.append(bool(ok))
    print('PASS' if ok else 'FAIL', name, '' if ok else f'  <-- {detail}')


def close(a, b) -> bool:
    return abs(float(a) - float(b)) < 1e-6


class Client(Api):
    """API client which can also return the status of a refused request."""

    def raw(self, method: str, url: str, data=None):
        return self.session.request(method, f'{self.base}{url}', json=data)

    def status(self, method: str, url: str, data=None) -> int:
        return self.raw(method, url, data).status_code

    def refused(self, method: str, url: str, data=None) -> tuple[int, str]:
        response = self.raw(method, url, data)

        return response.status_code, response.text

    def all(self, url: str) -> list:
        joiner = '&' if '?' in url else '?'
        data = self.get(f'{url}{joiner}limit=5000')

        return data['results'] if isinstance(data, dict) else data

    def setting(self, key: str, value):
        self.patch(f'/api/plugins/virtual-bins/settings/{key}/', {'value': value})


def stock_total(api: Client, part: int, location: int, *, available_only=False) -> float:
    """What InvenTree itself reports for a part in a location and below it."""
    rows = api.all(f'/api/stock/?part={part}&location={location}&cascade=true')
    total = 0.0

    for row in rows:
        if float(row['quantity']) <= 0:
            continue

        if available_only and not row['in_stock']:
            continue

        total += float(row['quantity'])

    return total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('base')
    parser.add_argument('token')
    parser.add_argument('--viewer')
    parser.add_argument('--operator')
    parser.add_argument('--nobody')
    args = parser.parse_args()

    api = Client(args.base, args.token)
    tag = uuid.uuid4().hex[:6]
    U = '/plugin/virtual-bins'

    # ------------------------------------------------------------------ setup

    category = api.post('/api/part/category/', {'name': f'VB check {tag}'})['pk']

    def part(name, **kwargs):
        return api.post('/api/part/', {
            'name': f'{name} {tag}', 'description': name, 'category': category,
            'component': True, **kwargs,
        })['pk']

    A = part('Alpha', IPN=f'VB-A-{tag}', units='pcs')
    B = part('Bravo')
    C = part('Charlie serial', trackable=True)
    D = part('Delta glue')
    E = part('Echo')
    F = part('Foxtrot unused')
    V = part('Virtual', virtual=True)
    SUB = part('Sub-assembly', assembly=True)
    ASM = part('Assembly', assembly=True)

    def bom(parent, child, quantity, **kwargs):
        api.post('/api/bom/', {'part': parent, 'sub_part': child, 'quantity': quantity, **kwargs})

    bom(ASM, A, 2)
    bom(ASM, SUB, 1)
    bom(ASM, B, 1, optional=True)
    bom(ASM, D, 1, consumable=True)
    bom(SUB, A, 1)
    bom(SUB, E, 3)

    def location(name, parent=None, structural=False):
        return api.post('/api/stock/location/', {
            'name': f'{name} {tag}' if parent is None else name,
            'parent': parent, 'structural': structural,
        })['pk']

    root = location('VB root', structural=True)
    unit = location('Bench', root)
    child1 = location('Child 1', unit)
    child2 = location('Child 2', unit)
    store = location('Store', root)
    frame = location('Frame', root, structural=True)
    frame_bin = location('Frame bin', frame)
    plain = location('Plain', root)

    def stock(part_pk, where, quantity, **kwargs):
        return api.post('/api/stock/', {
            'part': part_pk, 'location': where, 'quantity': quantity, **kwargs
        })

    def stock_pk(created) -> int:
        return created[0]['pk'] if isinstance(created, list) else created['pk']

    a_old = stock_pk(stock(A, unit, 10))
    a_new = stock_pk(stock(A, unit, 5, batch='LOT2'))
    stock(A, child1, 4)
    stock(A, store, 100)
    stock(A, plain, 30)
    stock(B, unit, 7)
    stock(B, unit, 3, status=75)  # quarantined: in the bin, but not available
    stock(E, child2, 9)
    stock(D, child2, 2)
    stock(SUB, unit, 2)
    stock(E, store, 50)

    # ------------------------------------------------- a location without bins

    data = api.get(f'{U}/unit/{unit}/')
    check('unconfigured: says so', data['configured'] is False)
    check('unconfigured: counts the parts stocked there', data['setup']['parts'] == 5, data['setup'])
    check('unconfigured: counts the locations below', data['setup']['children'] == 2, data['setup'])
    check('unconfigured: refill list is a 404', api.status('GET', f'{U}/unit/{unit}/refill/') == 404)
    check('unknown location is a 404', api.status('GET', f'{U}/unit/99999999/') == 404)

    # Something else's metadata on the location must survive everything below
    api.patch(f'/api/metadata/stocklocation/{unit}/', {'metadata': {'other_plugin': {'keep': 1}}})

    # ---------------------------------------------------------- saving a layout

    def put(layout):
        return api.refused('PUT', f'{U}/unit/{unit}/layout/', {'layout': layout})

    def one(**values):
        return {'rows': [{'columns': [{'bins': [values]}]}]}

    for name, layout, expect in (
        ('a size which does not exist', one(part=A, size='xl'), 'size'),
        ('a level which is not a number', one(part=A, min='lots'), 'levels'),
        ('a fill level below the minimum', one(part=A, min=10, max=5), 'below its minimum'),
        ('a part which does not exist', one(part=99999999), 'does not exist'),
        ('a location which does not exist', one(location=99999999), 'does not exist'),
        ('a virtual part', one(part=V), 'virtual'),
        ('a product which is not an assembly', {'product': A, 'rows': []}, 'assembly'),
        ('a product which does not exist', {'product': 99999999, 'rows': []}, 'no longer exists'),
        ('something which is not a layout', 'text', 'object'),
        ('too many bins in a stack', {'rows': [{'columns': [{'bins': [{}] * 9}]}]}, 'stack'),
    ):
        code, text = put(layout)
        check(f'layout refused: {name}', code == 400 and expect in text, f'{code} {text[:160]}')

    check('layout: nothing was stored by the refused saves',
          api.get(f'{U}/unit/{unit}/')['configured'] is False)

    layout_in = {
        'kind': 'bench',
        'product': ASM,
        'rows': [
            {'name': 'Left', 'columns': [
                {'bins': [{'part': A, 'min': 20, 'max': 40, 'size': 'm'}]},            # 0: A anywhere in the unit
                {'bins': [{'part': A, 'location': child1, 'min': 2, 'max': 10},          # 1: A in child 1
                          {'part': B, 'min': 5}]},                                      # 2: B
                {'bins': [{'location': child2, 'label': 'Mixed'}]},                     # 3: all of child 2
            ]},
            {'name': 'Right', 'columns': [
                {'bins': [{'part': E, 'location': child2, 'min': 30, 'max': 60}]},      # 4: E in child 2
                {'bins': [{'part': SUB, 'min': 1}]},                                    # 5: sub-assemblies
                {'bins': [{'part': D}]},                                                # 6: consumable
                {'bins': [{'part': F, 'min': 5, 'max': 10}]},                            # 7: empty
                {'bins': [{'label': 'Spare'}]},                                         # 8: placeholder
                {'bins': [{'part': C}]},                                                # 9: serial-numbered
            ]},
        ],
    }

    code, text = put(layout_in)
    check('layout: a valid layout is saved', code == 200, text[:300])

    data = api.get(f'{U}/unit/{unit}/')
    layout = data['layout']
    ids = [item['id'] for row in layout['rows'] for column in row['columns'] for item in column['bins']]
    check('layout: every bin has an id of its own', len(ids) == 10 and len(set(ids)) == 10, ids)
    check('layout: rows and names are kept',
          [row['name'] for row in layout['rows']] == ['Left', 'Right'])
    check('layout: the product is kept', data['product']['pk'] == ASM)

    code, _ = put(layout)
    again = api.get(f'{U}/unit/{unit}/')['layout']
    check('layout: saving it again keeps the ids', code == 200 and again == layout)

    meta = api.get(f'/api/metadata/stocklocation/{unit}/')['metadata']
    check('layout: stored in the metadata of the location', 'virtual_bins' in meta)
    check('layout: other metadata of the location is untouched', meta.get('other_plugin') == {'keep': 1})

    b = [data['bins'][bin_id] for bin_id in ids]

    # ----------------------------------------------- quantities against InvenTree

    check('quantity: part anywhere in the unit matches InvenTree (incl. below)',
          close(b[0]['quantity'], stock_total(api, A, unit)) and close(b[0]['quantity'], 19),
          b[0]['quantity'])
    check('quantity: part in a location of its own matches InvenTree',
          close(b[1]['quantity'], stock_total(api, A, child1)) and close(b[1]['quantity'], 4))
    check('quantity: stock with an unavailable status is still in the bin',
          close(b[2]['quantity'], 10) and close(b[2]['available'], 7) and close(b[2]['held_back'], 3),
          b[2])
    check('quantity: available matches InvenTree "in stock"',
          close(b[2]['available'], stock_total(api, B, unit, available_only=True)))
    check('quantity: stock items are listed',
          sorted(item['pk'] for item in b[0]['items'])[:2] == sorted([a_old, a_new])
          and b[0]['item_count'] == 3)
    check('quantity: batch and status of an item are shown',
          any(item['batch'] == 'LOT2' for item in b[0]['items'])
          and any(not item['available'] for item in b[2]['items']))
    check('location bin: lists the parts in it',
          sorted(entry['part'] for entry in b[3]['contents']) == sorted([E, D])
          and close(b[3]['quantity'], 11), b[3]['contents'])
    check('location bin: title is its label', b[3]['title'] == 'Mixed')
    check('titles: part name by default', b[0]['title'] == f'Alpha {tag}')
    check('part details: IPN and units', b[0]['part']['ipn'] == f'VB-A-{tag}' and b[0]['part']['units'] == 'pcs')
    check('placeholder: unassigned and empty of numbers',
          b[8]['status'] == 'unassigned' and b[8]['bound'] is False and b[8]['fill'] is None)
    check('elsewhere: stock of the part outside the unit',
          close(b[0]['elsewhere'], 130) and close(b[4]['elsewhere'], 50) and close(b[7]['elsewhere'], 0),
          (b[0]['elsewhere'], b[4]['elsewhere']))

    # ------------------------------------------------------------------- levels

    check('status: below minimum', b[0]['status'] == 'low' and b[4]['status'] == 'low')
    check('status: OK at or above minimum', b[1]['status'] == 'ok' and b[2]['status'] == 'ok')
    check('status: empty', b[7]['status'] == 'empty')
    check('status: no minimum is OK while it holds anything', b[6]['status'] == 'ok')
    check('fill: against the level it is filled to', close(b[0]['fill'], 19 / 40) and close(b[1]['fill'], 0.4))
    check('fill: against twice the minimum when there is no fill level', close(b[2]['fill'], 1.0))
    check('fill: none without levels', b[6]['fill'] is None)
    check('refill: up to the fill level when below minimum',
          close(b[0]['refill'], 21) and close(b[4]['refill'], 51) and close(b[7]['refill'], 10))
    check('refill: nothing when at or above minimum', close(b[1]['refill'], 0) and close(b[2]['refill'], 0))
    check('summary: adds up',
          data['summary'] == {'bins': 10, 'ok': 5, 'low': 2, 'empty': 2, 'unassigned': 1},
          data['summary'])

    # ------------------------------------------------------------ units covered

    check('per unit: summed over every level of the BOM',
          close(b[0]['per_unit'], 3) and close(b[4]['per_unit'], 3) and close(b[5]['per_unit'], 1),
          (b[0]['per_unit'], b[4]['per_unit'], b[5]['per_unit']))
    check('per unit: optional lines are left out', b[2]['per_unit'] is None and b[2]['covers'] is None)
    check('per unit: a consumable is marked and not counted',
          b[6]['consumable'] is True and b[6]['per_unit'] is None)
    check('per unit: a part which is not on the BOM has none', b[7]['per_unit'] is None)
    check('covers: whole units from what is available',
          b[0]['covers'] == 6 and b[1]['covers'] == 1 and b[4]['covers'] == 3 and b[5]['covers'] == 2,
          (b[0]['covers'], b[1]['covers'], b[4]['covers'], b[5]['covers']))

    # Units which can be built. Bins 0 and 1 both hold A: bin 0 shows the
    # whole unit (19), bin 1 the 4 of those which are in child 1, so there
    # are 19 and not 23. Sub-assemblies: 2 in stock, and more can be made
    # (A and E both have bins). n units need 2n A + (n-2) x (1 A + 3 E).
    #   n = 5: A 10 + 3 = 13 <= 19, E 9 <= 9      -> possible
    #   n = 6: A 12 + 4 = 16 <= 19, E 12 > 9      -> E runs out
    check('buildable: nets off sub-assemblies and makes more from their parts',
          data['buildable']['units'] == 5, data['buildable'])
    check('buildable: names the bin which runs out first',
          data['buildable']['limited_by'] == [ids[4]], data['buildable'])

    api.setting('INCLUDE_OPTIONAL', True)
    with_optional = api.get(f'{U}/unit/{unit}/')
    check('setting: optional lines can be counted',
          close(with_optional['bins'][ids[2]]['per_unit'], 1) and with_optional['bins'][ids[2]]['covers'] == 7)
    api.setting('INCLUDE_OPTIONAL', False)

    # ----------------------------------------------------- duplicates, positions

    check('position: in words', b[1]['position'] == 'Left, column 2, top'
          and b[2]['position'] == 'Left, column 2, bottom' and b[4]['position'] == 'Right, column 1',
          (b[1]['position'], b[2]['position'], b[4]['position']))
    check('duplicates: none in this layout', all(not item['duplicates'] for item in b))

    doubled = {**layout, 'rows': layout['rows'] + [{'name': 'Twice', 'columns': [{'bins': [{'part': A}]}]}]}
    put(doubled)
    twice = api.get(f'{U}/unit/{unit}/')
    extra_id = twice['layout']['rows'][2]['columns'][0]['bins'][0]['id']
    check('duplicates: two bins showing the same stock point at each other',
          twice['bins'][extra_id]['duplicates'] == [ids[0]] and twice['bins'][ids[0]]['duplicates'] == [extra_id])
    check('duplicates: the same stock is counted once for the units which can be built',
          twice['buildable']['units'] == 5, twice['buildable'])
    put(layout)

    # ------------------------------------------------------------ list of units

    units = api.get(f'{U}/units/')['units']
    mine = next((entry for entry in units if entry['location']['pk'] == unit), None)
    check('units: the unit is listed with the same summary',
          mine is not None and mine['summary'] == data['summary'] and mine['buildable'] == data['buildable'])
    check('units: bins which need attention are listed',
          mine is not None and sorted(item['id'] for item in mine['attention'])
          == sorted([ids[0], ids[4], ids[7], ids[9]]),
          mine and [item['title'] for item in mine['attention']])
    attention = api.get(f'{U}/attention/')
    check('attention: empty bins come first',
          attention['bins'] and attention['bins'][0]['status'] == 'empty'
          and any(item['unit'] == unit and item['id'] == ids[7] for item in attention['bins']))

    # ------------------------------------------------------------------ counting

    def adjust(bin_id, payload, client=api, where=unit):
        return client.refused('POST', f'{U}/unit/{where}/bin/{bin_id}/adjust/', payload)

    def ok(bin_id, payload, client=api, where=unit):
        response = client.raw('POST', f'{U}/unit/{where}/bin/{bin_id}/adjust/', payload)

        if response.status_code != 200:
            raise SystemExit(f'adjust {payload} -> {response.status_code}: {response.text[:300]}')

        return response.json()

    def item_qty(pk) -> float | None:
        response = api.raw('GET', f'/api/stock/{pk}/')

        return float(response.json()['quantity']) if response.status_code == 200 else None

    # Bin 1 (A in child 1, one item of 4) and bin 0 (A in the unit: 10 + 5 + the 4 below)
    result = ok(ids[0], {'action': 'count', 'quantity': 13, 'notes': f'check {tag}'})
    check('count down: takes from the oldest item first',
          close(item_qty(a_old), 4) and close(item_qty(a_new), 5), (item_qty(a_old), item_qty(a_new)))
    check('count down: InvenTree agrees with the count', close(stock_total(api, A, unit), 13))
    check('count: the answer describes the change',
          result['done'] == {'action': 'count', 'before': 19.0, 'after': 13.0}, result['done'])
    check('count: the answer carries the unit as it is now',
          close(result['unit']['bins'][ids[0]]['quantity'], 13))
    check('count: remembers when, by whom and how many',
          result['unit']['bins'][ids[0]]['counted']['by'] == 'admin'
          and close(result['unit']['bins'][ids[0]]['counted']['quantity'], 13))

    history = api.all(f'/api/audit/?model_type=stock.stockitem&model_id={a_old}')
    check('count: the note is in the stock history',
          any(entry.get('notes') == f'check {tag}' for entry in history),
          [entry.get('notes') for entry in history][:4])

    result = ok(ids[0], {'action': 'count', 'quantity': 13})
    check('count as expected: nothing changes, and it is recorded',
          close(stock_total(api, A, unit), 13) and result['done']['before'] == result['done']['after'])

    child_item = max(item['pk'] for item in result['unit']['bins'][ids[1]]['items'])
    result = ok(ids[0], {'action': 'count', 'quantity': 20})
    check('count up: the surplus goes onto the newest item',
          close(item_qty(child_item), 11) and close(item_qty(a_old), 4) and close(item_qty(a_new), 5),
          (item_qty(child_item), item_qty(a_old), item_qty(a_new)))

    ok(ids[1], {'action': 'count', 'quantity': 4})
    check('count: a bin with its own location only changes that location',
          close(stock_total(api, A, child1), 4) and close(stock_total(api, A, unit), 13))

    result = ok(ids[1], {'action': 'count', 'quantity': 0})
    check('count to zero: the bin is empty',
          close(result['unit']['bins'][ids[1]]['quantity'], 0)
          and result['unit']['bins'][ids[1]]['status'] == 'empty')
    result = ok(ids[1], {'action': 'count', 'quantity': 6})
    made = result['unit']['bins'][ids[1]]['items']
    check('count of an empty bin: makes a stock item in the location of the bin',
          len(made) == 1 and made[0]['location'] == child1 and close(made[0]['quantity'], 6), made)

    result = ok(ids[7], {'action': 'count', 'quantity': 3})
    made = result['unit']['bins'][ids[7]]['items']
    check('count of an empty bin without its own location: stock goes into the unit',
          len(made) == 1 and made[0]['location'] == unit, made)

    for name, payload, expect in (
        ('a negative count', {'action': 'count', 'quantity': -1}, 'zero or more'),
        ('a count which is not a number', {'action': 'count', 'quantity': 'ten'}, 'zero or more'),
        ('a count with no quantity', {'action': 'count'}, 'zero or more'),
        ('adding nothing', {'action': 'add', 'quantity': 0}, 'above zero'),
        ('removing nothing', {'action': 'remove', 'quantity': 0}, 'above zero'),
        ('an unknown action', {'action': 'explode', 'quantity': 1}, 'Unknown action'),
        ('no action', {'quantity': 1}, 'Unknown action'),
    ):
        code, text = adjust(ids[0], payload)
        check(f'refused: {name}', code == 400 and expect in text, f'{code} {text[:160]}')

    code, text = adjust('nosuchbin', {'action': 'count', 'quantity': 1})
    check('refused: a bin which is not in the layout', code == 400 and 'no longer part' in text, text[:160])
    code, text = adjust(ids[8], {'action': 'count', 'quantity': 1})
    check('refused: counting a placeholder', code == 400 and 'not set to a part' in text, text[:160])
    code, text = adjust(ids[3], {'action': 'count', 'quantity': 1})
    check('refused: counting a bin which shows a whole location', code == 400 and 'not set to a part' in text)
    check('refused: a location without bins',
          api.status('POST', f'{U}/unit/{plain}/bin/x/adjust/', {'action': 'count', 'quantity': 1}) == 404)

    # ------------------------------------------------------------- add and remove

    before = stock_total(api, A, unit)
    result = ok(ids[0], {'action': 'add', 'quantity': 2.5})
    check('add: InvenTree has that much more', close(stock_total(api, A, unit), before + 2.5))
    newest = max(result['unit']['bins'][ids[0]]['items'], key=lambda entry: entry['pk'])
    check('add: goes onto the newest item', close(newest['quantity'], 6 + 2.5), newest)

    result = ok(ids[0], {'action': 'remove', 'quantity': 6})
    check('remove: InvenTree has that much less', close(stock_total(api, A, unit), before + 2.5 - 6))
    check('remove: oldest stock goes first (the first item is used up)',
          item_qty(a_old) in (None, 0.0) and close(item_qty(a_new), 3), (item_qty(a_old), item_qty(a_new)))

    code, text = adjust(ids[0], {'action': 'remove', 'quantity': 1000})
    check('refused: removing more than the bin holds',
          code == 400 and 'does not hold that much' in text, text[:160])
    check('refused removal changed nothing', close(stock_total(api, A, unit), before + 2.5 - 6))

    result = ok(ids[6], {'action': 'add', 'quantity': 1})
    check('add: a bin bound to the unit takes stock held in a location below it',
          close(result['unit']['bins'][ids[6]]['quantity'], 3))

    # ------------------------------------------------------------------- moving

    in_bin = stock_total(api, A, unit)
    in_plain = stock_total(api, A, plain)

    for name, payload, expect in (
        ('a move without a destination', {'action': 'move', 'quantity': 1}, 'Choose where'),
        ('a move to the location of the bin', {'action': 'move', 'quantity': 1, 'destination': unit}, 'location of this bin'),
        ('a move to a location inside the bin', {'action': 'move', 'quantity': 1, 'destination': child1}, 'location of this bin'),
        ('a move to a structural location', {'action': 'move', 'quantity': 1, 'destination': frame}, 'structural'),
        ('a move of more than the bin holds', {'action': 'move', 'quantity': 9999, 'destination': plain}, 'does not hold'),
    ):
        code, text = adjust(ids[0], payload)
        check(f'refused: {name}', code == 400 and expect in text, f'{code} {text[:160]}')

    result = ok(ids[0], {'action': 'move', 'quantity': 4, 'destination': plain})
    check('move: the stock leaves the bin and arrives at the destination',
          close(stock_total(api, A, unit), in_bin - 4) and close(stock_total(api, A, plain), in_plain + 4),
          (stock_total(api, A, unit), stock_total(api, A, plain)))
    check('move: the answer names the destination', result['done']['destination'].endswith('/Plain'))

    # ------------------------------------------------------------------ refills

    refill = api.get(f'{U}/unit/{unit}/refill/')
    lines = {line['bin']: line for line in refill['lines']}
    now = api.get(f'{U}/unit/{unit}/')
    due = {bin_id for bin_id, item in now['bins'].items() if item['refill'] > 0 and item['part']}
    check('refill list: exactly the bins which are due', set(lines) == due, (set(lines), due))
    check('refill list: in the order of the layout',
          [line['bin'] for line in refill['lines']] == [bin_id for bin_id in ids if bin_id in due])

    def item(pk) -> dict:
        return api.get(f'/api/stock/{pk}/')

    unit_tree = {unit, child1, child2}
    line = lines[ids[0]]
    check('refill list: sources are stock outside the unit, oldest first',
          len(line['sources']) >= 2
          and [source['pk'] for source in line['sources']] == sorted(source['pk'] for source in line['sources'])
          and all(source['location'] not in unit_tree for source in line['sources']),
          line['sources'])
    check('refill list: elsewhere is the total of what can be taken',
          close(line['elsewhere'], stock_total(api, A, store) + stock_total(api, A, plain)))
    check('refill list: a bin with nothing elsewhere has no sources',
          lines[ids[7]]['sources'] == [] and close(lines[ids[7]]['elsewhere'], 0))

    sources = api.get(f'{U}/unit/{unit}/bin/{ids[0]}/sources/')['sources']
    check('sources: the same list for the bin itself', [s['pk'] for s in sources] == [s['pk'] for s in line['sources']])
    check('sources: none for a placeholder', api.get(f'{U}/unit/{unit}/bin/{ids[8]}/sources/')['sources'] == [])

    # Top up by more than the oldest source holds: it is emptied, the next one gives the rest
    first, second = sources[0], sources[1]
    amount = first['quantity'] + 2
    in_bin = stock_total(api, A, unit)
    elsewhere = stock_total(api, A, store) + stock_total(api, A, plain)
    result = ok(ids[0], {'action': 'refill', 'quantity': amount})
    check('top up: the stock arrives in the bin and leaves the rest of the store',
          close(stock_total(api, A, unit), in_bin + amount)
          and close(stock_total(api, A, store) + stock_total(api, A, plain), elsewhere - amount))
    check('top up: the oldest stock elsewhere is taken first, then the next',
          item(first['pk'])['location'] == unit and close(item(second['pk'])['quantity'], second['quantity'] - 2),
          (item(first['pk'])['location'], item(second['pk'])['quantity']))
    check('top up: the answer names where it came from',
          len(result['done']['sources']) == 2
          and all('Bench' not in name for name in result['done']['sources']), result['done'])

    plain_item = max(
        api.get(f'{U}/unit/{unit}/bin/{ids[0]}/sources/')['sources'], key=lambda source: source['quantity']
    )['pk']
    held = item(plain_item)['quantity']
    in_bin = stock_total(api, A, unit)
    ok(ids[0], {'action': 'refill', 'quantity': 3, 'source': plain_item})
    check('top up: from the chosen stock item',
          close(item(plain_item)['quantity'], held - 3) and close(stock_total(api, A, unit), in_bin + 3))

    code, text = adjust(ids[0], {'action': 'refill', 'quantity': 5000, 'source': plain_item})
    check('refused: more than the chosen item holds', code == 400 and 'Only' in text, text[:160])
    code, text = adjust(ids[0], {'action': 'refill', 'quantity': 50000})
    check('refused: more than there is elsewhere', code == 400 and 'Only' in text, text[:160])
    other_item = stock_pk(stock(B, store, 5))
    code, text = adjust(ids[0], {'action': 'refill', 'quantity': 1, 'source': other_item})
    check('refused: a source which is another part', code == 400 and 'no longer available' in text, text[:160])
    code, text = adjust(ids[7], {'action': 'refill', 'quantity': 1})
    check('refused: topping up when there is none elsewhere', code == 400 and 'Only 0' in text, text[:160])

    in_child = stock_total(api, A, child1)
    ok(ids[1], {'action': 'refill', 'quantity': 2})
    check('top up: a bin with its own location is filled in that location',
          close(stock_total(api, A, child1), in_child + 2))

    # A span of items: more than the first source holds
    small = part('Golf spread')
    put({**layout, 'rows': layout['rows'] + [{'name': 'Extra', 'columns': [{'bins': [{'part': small, 'min': 1, 'max': 9}]}]}]})
    extra = api.get(f'{U}/unit/{unit}/')['layout']['rows'][2]['columns'][0]['bins'][0]['id']
    stock(small, store, 4)
    stock(small, plain, 4)
    result = ok(extra, {'action': 'refill', 'quantity': 6})
    check('top up: spreads over several items when the first is not enough',
          close(stock_total(api, small, unit), 6) and close(stock_total(api, small, store), 0)
          and close(stock_total(api, small, plain), 2) and len(result['done']['sources']) == 2,
          result['done'])

    # ----------------------------------------------------- serial-numbered stock

    serials = stock(C, unit, 2, serial_numbers='1,2')
    now = api.get(f'{U}/unit/{unit}/')
    check('serials: the bin shows them', now['bins'][ids[9]]['serialized'] is True
          and close(now['bins'][ids[9]]['quantity'], 2), serials and now['bins'][ids[9]]['quantity'])

    for action in ('count', 'add', 'remove'):
        code, text = adjust(ids[9], {'action': action, 'quantity': 1})
        check(f'refused: {action} of serial-numbered stock', code == 400 and 'serial-numbered' in text, text[:160])

    # ----------------------------------------------------- structural locations

    code, text = api.refused('PUT', f'{U}/unit/{frame}/layout/', {'layout': {
        'kind': 'shelving', 'rows': [{'columns': [
            {'bins': [{'part': A, 'min': 5, 'max': 10}]},
            {'bins': [{'part': A, 'location': frame_bin, 'min': 5, 'max': 10}]},
        ]}]}})
    check('structural unit: a layout can be saved on it', code == 200, text[:200])
    frame_data = api.get(f'{U}/unit/{frame}/')
    frame_ids = [item['id'] for item in frame_data['layout']['rows'][0]['columns'] for item in item['bins']]

    code, text = adjust(frame_ids[0], {'action': 'count', 'quantity': 3}, where=frame)
    check('refused: counting stock into a structural location', code == 400 and 'structural' in text, text[:200])
    code, text = adjust(frame_ids[0], {'action': 'refill', 'quantity': 3}, where=frame)
    check('refused: topping up into a structural location', code == 400 and 'structural' in text, text[:200])
    ok(frame_ids[1], {'action': 'count', 'quantity': 3}, where=frame)
    check('structural unit: a bin with a location of its own can hold stock',
          close(stock_total(api, A, frame_bin), 3))
    check('structural unit: the bin bound to the unit sees the stock below',
          close(api.get(f'{U}/unit/{frame}/')['bins'][frame_ids[0]]['quantity'], 3))

    # ------------------------------------------------------------ made layouts

    stored = api.get(f'{U}/unit/{unit}/')['layout']

    made = api.post(f'{U}/unit/{unit}/autofill/', {'source': 'stock'})
    parts_made = [item['part'] for row in made['layout']['rows'] for column in row['columns'] for item in column['bins']]
    in_unit = {row['part'] for row in api.all(f'/api/stock/?location={unit}&cascade=true') if float(row['quantity']) > 0}
    check('from stock: one bin for each part stocked in the unit or below',
          sorted(parts_made) == sorted(in_unit) and made['found'] == len(in_unit), (parts_made, in_unit))
    check('from stock: names of the parts come with it', str(A) in made['parts'] or A in made['parts'])

    made = api.post(f'{U}/unit/{unit}/autofill/', {'source': 'children'})
    cells = [(item['part'], item['location']) for row in made['layout']['rows'] for column in row['columns'] for item in column['bins']]
    check('from locations: one bin for each location below, with its part if it holds one',
          cells == [(A, child1), (None, child2)], cells)
    check('from locations: names of the locations come with it',
          {entry['name'] for entry in made['locations'].values()} == {'Child 1', 'Child 2'}, made['locations'])

    made = api.post(f'{U}/unit/{unit}/autofill/', {'source': 'bom', 'assembly': ASM, 'levels': 'direct'})
    parts_made = [item['part'] for row in made['layout']['rows'] for column in row['columns'] for item in column['bins']]
    check('from a BOM: its own lines, in BOM order', parts_made == [A, SUB, B, D] and made['layout']['product'] == ASM, parts_made)

    made = api.post(f'{U}/unit/{unit}/autofill/', {'source': 'bom', 'assembly': ASM, 'levels': 'all'})
    parts_made = [item['part'] for row in made['layout']['rows'] for column in row['columns'] for item in column['bins']]
    check('from a BOM: every level', parts_made == [A, SUB, E, B, D], parts_made)

    made = api.post(f'{U}/unit/{unit}/autofill/', {'source': 'bom', 'assembly': ASM, 'levels': 'all', 'layout': stored})
    kept = [item['id'] for row in made['layout']['rows'] for column in row['columns'] for item in column['bins']]
    check('added to a layout: existing bins stay, only missing ones are added',
          kept[: len(ids) + 1] == ids + [extra] and made['added'] == 0, (made['added'], made['found']))

    made = api.post(f'{U}/unit/{unit}/autofill/', {'source': 'stock', 'layout': {'rows': [{'columns': [{'bins': [{'part': B}]}]}]}})
    check('added to a layout: reports how many were new',
          made['added'] == made['found'] - 1, (made['added'], made['found']))

    check('made layouts: nothing was saved', api.get(f'{U}/unit/{unit}/')['layout'] == stored)

    for name, payload, expect in (
        ('an unknown source', {'source': 'magic'}, 'Unknown source'),
        ('a BOM without an assembly', {'source': 'bom'}, 'Choose an assembly'),
        ('a BOM of a part which is not an assembly', {'source': 'bom', 'assembly': A}, 'not an assembly'),
    ):
        code, text = api.refused('POST', f'{U}/unit/{unit}/autofill/', payload)
        check(f'refused: {name}', code == 400 and expect in text, f'{code} {text[:160]}')

    # ------------------------------------------------------------------- locate

    def locate(payload):
        """Press "Locate", and wait for the request to show up for the unit."""
        seen = {match['at'] for match in api.get(f'{U}/locate/?unit={unit}')['matches']}
        response = api.raw('POST', '/api/locate/', {'plugin': 'virtual-bins', **payload})

        if response.status_code != 200:
            return None

        for _ in range(40):
            fresh = [
                match for match in api.get(f'{U}/locate/?unit={unit}')['matches']
                if match['at'] not in seen
            ]

            if fresh:
                return fresh

            time.sleep(0.5)

        return []

    matches = locate({'location': child1})
    check('locate a location: the bin which is that location flashes',
          matches and ids[1] in matches[-1]['bins'] and ids[0] not in matches[-1]['bins'], matches)

    in_unit_item = api.get(f'{U}/unit/{unit}/')['bins'][ids[0]]['items'][0]['pk']
    matches = locate({'item': in_unit_item})
    check('locate a stock item: the bin of its part flashes',
          matches and ids[0] in matches[-1]['bins'] and ids[2] not in matches[-1]['bins'], matches)

    matches = locate({'location': unit})
    check('locate the unit itself: the whole unit flashes',
          matches and any(match['unit'] and not match['bins'] for match in matches), matches)

    listing = api.get(f'{U}/locate/')
    check('locate: the units with something to show are listed', unit in listing['units'], listing)
    check('locate: how long a bin flashes comes from the settings', listing['seconds'] == 20)

    # This waits for the highlight time to pass, so it comes last
    outside = stock_pk(stock(A, store, 1))
    check('locate something in another place: nothing flashes here', locate({'item': outside}) == [])
    check('locate: requests are forgotten after the highlight time',
          api.get(f'{U}/locate/?unit={unit}')['matches'] == [])

    # ----------------------------------------------------------------- settings

    api.setting('REFRESH_SECONDS', 45)
    api.setting('BLIND_COUNT', True)
    config = api.get(f'{U}/config/')
    check('settings: reach the interface',
          config['settings']['refresh_seconds'] == 45 and config['settings']['blind_count'] is True)
    api.setting('REFRESH_SECONDS', 30)
    api.setting('BLIND_COUNT', False)
    check('config: version and limits', config['version'] and config['limits']['stack'] == 8)

    features = api.get(f'/api/plugins/ui/features/panel/?target_model=stocklocation&target_id={unit}')
    check('interface: a Bins panel on the location page',
          any(feature['plugin_name'] == 'virtual-bins' for feature in features))
    features = api.get(f'/api/plugins/ui/features/panel/?target_model=part&target_id={A}')
    check('interface: no panel on other pages',
          not any(feature['plugin_name'] == 'virtual-bins' for feature in features))
    api.setting('PANEL_CONFIGURED_ONLY', True)
    features = api.get(f'/api/plugins/ui/features/panel/?target_model=stocklocation&target_id={store}')
    check('setting: the panel can be limited to locations which have bins',
          not any(feature['plugin_name'] == 'virtual-bins' for feature in features))
    api.setting('PANEL_CONFIGURED_ONLY', False)
    features = api.get(f'/api/plugins/ui/features/panel/?target_model=stocklocation&target_id={store}')
    check('interface: by default the panel is on every location for people who can set it up',
          any(feature['plugin_name'] == 'virtual-bins' for feature in features))

    for kind in ('navigation', 'dashboard', 'route'):
        features = api.get(f'/api/plugins/ui/features/{kind}/')
        check(f'interface: {kind} item', any(feature['plugin_name'] == 'virtual-bins' for feature in features))

    # -------------------------------------------------------------- permissions

    anonymous = requests.Session()
    anonymous.trust_env = False
    check('anonymous: refused',
          anonymous.get(f'{api.base}{U}/unit/{unit}/', allow_redirects=False).status_code in (401, 403))

    if args.viewer:
        viewer = Client(args.base, args.viewer)
        seen = viewer.get(f'{U}/unit/{unit}/')
        check('viewer: sees the unit', seen['configured'] and seen['permissions'] == {
            'view': True, 'layout': False, 'adjust': False, 'add': False})
        check('viewer: sees the list, the refill list and the dashboard numbers',
              viewer.status('GET', f'{U}/units/') == 200 and viewer.status('GET', f'{U}/unit/{unit}/refill/') == 200
              and viewer.status('GET', f'{U}/attention/') == 200)
        check('viewer: may not save a layout', viewer.status('PUT', f'{U}/unit/{unit}/layout/', {'layout': stored}) == 403)
        check('viewer: may not remove a layout', viewer.status('DELETE', f'{U}/unit/{unit}/layout/') == 403)
        check('viewer: may not make a layout', viewer.status('POST', f'{U}/unit/{unit}/autofill/', {'source': 'stock'}) == 403)
        check('viewer: may not change stock', adjust(ids[0], {'action': 'count', 'quantity': 1}, client=viewer)[0] == 403)
        features = viewer.get(f'/api/plugins/ui/features/panel/?target_model=stocklocation&target_id={store}')
        check('viewer: no panel on a location without bins',
              not any(feature['plugin_name'] == 'virtual-bins' for feature in features))
        features = viewer.get(f'/api/plugins/ui/features/panel/?target_model=stocklocation&target_id={unit}')
        check('viewer: the panel on a location with bins',
              any(feature['plugin_name'] == 'virtual-bins' for feature in features))
    else:
        print('SKIP viewer checks (no --viewer token)')

    if args.operator:
        operator = Client(args.base, args.operator)
        before = stock_total(api, B, unit)
        code, text = adjust(ids[2], {'action': 'count', 'quantity': before + 1}, client=operator)
        check('operator: may count', code == 200 and close(stock_total(api, B, unit), before + 1), text[:200])
        check('operator: may not save a layout', operator.status('PUT', f'{U}/unit/{unit}/layout/', {'layout': stored}) == 403)

        ok(ids[7], {'action': 'count', 'quantity': 0})
        code, text = adjust(ids[7], {'action': 'count', 'quantity': 2}, client=operator)
        check('operator without "add": a count which needs a new stock item is refused',
              code == 400 and 'permission to add' in text, text[:200])
        code, text = adjust(ids[7], {'action': 'add', 'quantity': 2}, client=operator)
        check('operator without "add": adding to an empty bin is refused',
              code == 400 and 'permission to add' in text, text[:200])
        check('operator: the refused changes made no stock', close(stock_total(api, F, unit), 0))
    else:
        print('SKIP operator checks (no --operator token)')

    if args.nobody:
        nobody = Client(args.base, args.nobody)
        codes = [
            nobody.status('GET', f'{U}/config/'),
            nobody.status('GET', f'{U}/units/'),
            nobody.status('GET', f'{U}/unit/{unit}/'),
            nobody.status('GET', f'{U}/attention/'),
            nobody.status('GET', f'{U}/locate/'),
            nobody.status('PUT', f'{U}/unit/{unit}/layout/', {'layout': stored}),
            adjust(ids[0], {'action': 'count', 'quantity': 1}, client=nobody)[0],
        ]
        check('no roles: everything is refused', codes == [403] * 7, codes)

        for kind in ('navigation', 'dashboard'):
            features = nobody.get(f'/api/plugins/ui/features/{kind}/')
            check(f'no roles: no {kind} item',
                  not any(feature['plugin_name'] == 'virtual-bins' for feature in features))
    else:
        print('SKIP no-role checks (no --nobody token)')

    # ------------------------------------------------- things which go missing

    gone_part = part('Hotel gone')
    gone_location = location('Gone', unit)
    put({**stored, 'rows': stored['rows'] + [{'name': 'Gone', 'columns': [
        {'bins': [{'part': gone_part}]}, {'bins': [{'location': gone_location}]},
    ]}]})
    with_gone = api.get(f'{U}/unit/{unit}/')
    gone_ids = [item['id'] for column in with_gone['layout']['rows'][-1]['columns'] for item in column['bins']]
    api.patch(f'/api/part/{gone_part}/', {'active': False})
    api.call('DELETE', f'/api/part/{gone_part}/')
    api.call('DELETE', f'/api/stock/location/{gone_location}/',
             {'delete_stock_items': False, 'delete_sub_locations': False})

    after = api.raw('GET', f'{U}/unit/{unit}/')
    check('missing: the unit still loads after a part and a location are deleted', after.status_code == 200)

    if after.status_code == 200:
        after = after.json()
        check('missing: the bin says its part is gone',
              after['bins'][gone_ids[0]]['part_missing'] is True and after['bins'][gone_ids[0]]['part'] is None)
        check('missing: the bin says its location is gone',
              after['bins'][gone_ids[1]]['location_missing'] is True)
        code, text = adjust(gone_ids[0], {'action': 'count', 'quantity': 1})
        check('missing: stock of a deleted part cannot be changed', code == 400 and 'no longer exists' in text, text[:200])

    put(stored)

    # ------------------------------------------------------- removing the layout

    check('remove: the layout is removed', api.status('DELETE', f'{U}/unit/{unit}/layout/') == 204)
    data = api.get(f'{U}/unit/{unit}/')
    check('remove: the location has no bins again', data['configured'] is False)
    meta = api.get(f'/api/metadata/stocklocation/{unit}/')['metadata']
    check('remove: nothing of the plugin is left in the metadata',
          'virtual_bins' not in meta and 'virtual_bins_state' not in meta, list(meta))
    check('remove: other metadata is still there', meta.get('other_plugin') == {'keep': 1})
    check('remove: the unit is no longer listed',
          not any(entry['location']['pk'] == unit for entry in api.get(f'{U}/units/')['units']))
    check('remove: the stock is untouched', stock_total(api, A, unit) > 0)
    check('remove: removing it again is harmless', api.status('DELETE', f'{U}/unit/{unit}/layout/') == 204)

    api.call('DELETE', f'{U}/unit/{frame}/layout/')

    passed = sum(results)
    print(f'\n{passed} of {len(results)} checks passed')

    if passed != len(results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
