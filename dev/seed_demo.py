"""Seed an InvenTree development instance with demo data for the Virtual Bins plugin.

Creates a made-up product ("Outdoor Sensor Node") with its BOM, a small
factory (an assembly bench, a packing bench, a shelving unit and bulk storage),
stock in all of them, and the bin layouts of the three units.

    python dev/seed_demo.py http://localhost:8000 <api token>

Only run this against a throwaway database.
"""

from __future__ import annotations

import sys

import requests


class Api:
    """Minimal InvenTree API client."""

    def __init__(self, base: str, token: str):
        self.base = base.rstrip('/')
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers['Authorization'] = f'Token {token}'

    def call(self, method: str, url: str, data=None):
        response = self.session.request(method, f'{self.base}{url}', json=data)

        if response.status_code >= 400:
            raise SystemExit(f'{method} {url} -> {response.status_code}: {response.text[:400]}')

        return response.json() if response.content else {}

    def post(self, url: str, data=None):
        return self.call('POST', url, data or {})

    def get(self, url: str):
        return self.call('GET', url)

    def put(self, url: str, data=None):
        return self.call('PUT', url, data or {})

    def patch(self, url: str, data=None):
        return self.call('PATCH', url, data or {})


def bin_(part=None, location=None, size='s', low=None, high=None, label='', note=''):
    return {
        'part': part,
        'location': location,
        'size': size,
        'min': low,
        'max': high,
        'label': label,
        'note': note,
    }


def main(base: str, token: str):
    api = Api(base, token)
    api.get('/plugin/virtual-bins/config/')

    # Categories
    cats = {}

    for name in ('Products', 'Sub-assemblies', 'Electronics', 'Mechanical', 'Fasteners',
                 'Packaging', 'Consumables'):
        cats[name] = api.post('/api/part/category/', {'name': name})['pk']

    # Parts
    parts = {}

    def part(key, name, category, ipn, description='', **kwargs):
        parts[key] = api.post('/api/part/', {
            'name': name,
            'IPN': ipn,
            'description': description or name,
            'category': cats[category],
            'component': True,
            'purchaseable': not kwargs.get('assembly', False),
            **kwargs,
        })['pk']

    part('node', 'Outdoor Sensor Node', 'Products', 'OSN-100',
         'Battery powered outdoor sensor', assembly=True, salable=True)
    part('boxed', 'Outdoor Sensor Node, boxed', 'Products', 'OSN-100-B',
         'Sensor node packed for shipping', assembly=True, salable=True)
    part('battery', 'Battery pack', 'Sub-assemblies', 'SA-210',
         'Two cell pack with lead', assembly=True)

    part('pcba', 'Main board PCBA', 'Electronics', 'EL-301')
    part('radio', 'Radio module', 'Electronics', 'EL-302')
    part('antenna', 'Antenna, stub', 'Electronics', 'EL-303')
    part('cell', 'Li-ion cell 18650', 'Electronics', 'EL-310')
    part('holder', 'Battery holder, 2 cell', 'Electronics', 'EL-311')
    part('lead', 'Battery lead, 80 mm', 'Electronics', 'EL-312')

    part('base', 'Enclosure base', 'Mechanical', 'ME-401')
    part('lid', 'Enclosure lid', 'Mechanical', 'ME-402')
    part('gasket', 'Lid gasket', 'Mechanical', 'ME-403')
    part('gland', 'Cable gland M12', 'Mechanical', 'ME-404')
    part('vent', 'Vent membrane', 'Mechanical', 'ME-405')
    part('bracket', 'Mounting bracket', 'Mechanical', 'ME-406')

    part('screw', 'Screw M3x10, pan head', 'Fasteners', 'FA-501')
    part('washer', 'Washer M3, nylon', 'Fasteners', 'FA-502')
    part('screw_b', 'Screw M4x12, bracket', 'Fasteners', 'FA-503')

    part('label', 'Product label', 'Packaging', 'PK-601')
    part('desiccant', 'Desiccant pack 2 g', 'Packaging', 'PK-602')
    part('carton', 'Carton, 150 mm', 'Packaging', 'PK-610')
    part('foam', 'Foam insert', 'Packaging', 'PK-611')
    part('card', 'Quick-start card', 'Packaging', 'PK-612')
    part('carton_label', 'Carton label', 'Packaging', 'PK-613')
    part('seal', 'Tamper seal', 'Packaging', 'PK-614')

    part('threadlock', 'Thread locker, blue', 'Consumables', 'CO-701')
    part('tape', 'Polyimide tape 12 mm', 'Consumables', 'CO-702')

    # Bills of materials
    def bom(parent, child, quantity, **kwargs):
        api.post('/api/bom/', {
            'part': parts[parent], 'sub_part': parts[child], 'quantity': quantity, **kwargs
        })

    for child, quantity in (('pcba', 1), ('radio', 1), ('antenna', 1), ('battery', 1),
                            ('base', 1), ('lid', 1), ('gasket', 1), ('gland', 2), ('vent', 1),
                            ('bracket', 1), ('screw', 4), ('washer', 4), ('screw_b', 2),
                            ('label', 1), ('desiccant', 1)):
        bom('node', child, quantity)

    bom('node', 'threadlock', 1, consumable=True)

    for child, quantity in (('cell', 2), ('holder', 1), ('lead', 1)):
        bom('battery', child, quantity)

    bom('battery', 'tape', 1, consumable=True)

    for child, quantity in (('node', 1), ('carton', 1), ('foam', 1), ('card', 1),
                            ('carton_label', 2), ('seal', 2)):
        bom('boxed', child, quantity)

    # Stock locations
    def location(name, parent=None, structural=False, description=''):
        return api.post('/api/stock/location/', {
            'name': name, 'parent': parent, 'structural': structural, 'description': description,
        })['pk']

    factory = location('Factory', structural=True)
    bench = location('Assembly bench 1', factory, description='Final assembly of the sensor node')
    packing = location('Packing bench', factory, description='Boxing and labelling')
    stores = location('Stores', structural=True)
    shelving = location('Shelving unit A', stores, description='Small parts, one location per bin')
    bulk = location('Bulk storage', stores, description='Full boxes and reels')

    shelf_bins = {}

    for row in (1, 2, 3):
        for column in (1, 2, 3, 4):
            code = f'A{row}-{column}'
            shelf_bins[code] = location(code, shelving)

    # Stock
    def stock(key, where, quantity, **kwargs):
        if quantity > 0:
            api.post('/api/stock/', {
                'part': parts[key], 'location': where, 'quantity': quantity, **kwargs
            })

    # On the assembly bench: a working mix, with a few bins running out
    bench_stock = {
        'pcba': 18, 'radio': 22, 'antenna': 9, 'battery': 14, 'cell': 46, 'holder': 30,
        'lead': 0, 'base': 16, 'lid': 16, 'gasket': 40, 'gland': 26, 'vent': 55,
        'bracket': 12, 'screw': 420, 'washer': 60, 'screw_b': 180, 'label': 75,
        'desiccant': 8, 'threadlock': 2,
    }

    for key, quantity in bench_stock.items():
        stock(key, bench, quantity)

    # A second batch of cells in the same bin, and a few quarantined boards
    stock('cell', bench, 20, batch='LOT-0412')
    stock('pcba', bench, 3, status=75, batch='RMA-17')

    # On the packing bench
    for key, quantity in {'node': 6, 'carton': 34, 'foam': 30, 'card': 12,
                          'carton_label': 150, 'seal': 0}.items():
        stock(key, packing, quantity)

    # Bulk storage: where refills come from (nothing held of some parts)
    for key, quantity in {'pcba': 60, 'radio': 80, 'antenna': 100, 'cell': 400, 'holder': 120,
                          'lead': 200, 'base': 48, 'lid': 48, 'gasket': 300, 'gland': 150,
                          'vent': 500, 'screw': 5000, 'washer': 5000, 'screw_b': 1000,
                          'label': 1000, 'carton': 200, 'foam': 200, 'card': 500,
                          'carton_label': 2000, 'seal': 1000}.items():
        stock(key, bulk, quantity)

    # Shelving unit: one part per bin location, one mixed bin and one empty bin
    shelf_stock = {
        'A1-1': [('radio', 40)], 'A1-2': [('antenna', 35)], 'A1-3': [('holder', 12)],
        'A1-4': [('lead', 90)],
        'A2-1': [('gland', 6)], 'A2-2': [('vent', 120)], 'A2-3': [('gasket', 64)],
        'A2-4': [('bracket', 0)],
        'A3-1': [('screw', 900)], 'A3-2': [('washer', 1500)], 'A3-3': [('screw_b', 300)],
        'A3-4': [('threadlock', 4), ('tape', 6)],
    }

    for code, held in shelf_stock.items():
        for key, quantity in held:
            stock(key, shelf_bins[code], quantity)

    # Layouts
    p = parts

    api.put(f'/plugin/virtual-bins/unit/{bench}/layout/', {'layout': {
        'kind': 'bench',
        'product': p['node'],
        'rows': [
            {'name': 'Left bay', 'columns': [
                {'bins': [bin_(p['pcba'], size='m', low=10, high=30)]},
                {'bins': [bin_(p['radio'], low=10, high=30), bin_(p['antenna'], low=10, high=30)]},
                {'bins': [bin_(p['battery'], size='m', low=8, high=24)]},
                {'bins': [bin_(p['cell'], low=40, high=120), bin_(p['holder'], low=20, high=60),
                          bin_(p['lead'], low=20, high=60)]},
                {'bins': [bin_(p['base'], size='l', low=8, high=24)]},
                {'bins': [bin_(p['lid'], size='l', low=8, high=24)]},
                {'bins': [bin_(p['gasket'], low=20, high=80)]},
            ]},
            {'name': 'Right bay', 'columns': [
                {'bins': [bin_(p['gland'], low=30, high=100), bin_(p['vent'], low=20, high=100)]},
                {'bins': [bin_(p['bracket'], size='m', low=8, high=24)]},
                {'bins': [bin_(p['screw'], low=200, high=1000), bin_(p['washer'], low=200, high=1000)]},
                {'bins': [bin_(p['screw_b'], low=100, high=500)]},
                {'bins': [bin_(p['label'], low=40, high=200), bin_(p['desiccant'], low=20, high=100)]},
                {'bins': [bin_(p['threadlock'], low=1, high=4, note='Replace when a bottle is opened')]},
                {'bins': [bin_(label='Spare bin')]},
            ]},
        ],
    }})

    api.put(f'/plugin/virtual-bins/unit/{packing}/layout/', {'layout': {
        'kind': 'bench',
        'product': p['boxed'],
        'rows': [{'name': '', 'columns': [
            {'bins': [bin_(p['node'], size='l', low=4, high=20, label='Tested units')]},
            {'bins': [bin_(p['card'], low=20, high=100)]},
            {'bins': [bin_(p['carton_label'], low=40, high=400)]},
            {'bins': [bin_(p['seal'], low=40, high=400)]},
            {'bins': [bin_(p['foam'], size='l', low=10, high=40)]},
            {'bins': [bin_(p['carton'], size='l', low=10, high=40)]},
        ]}],
    }})

    single = {
        'A1-1': 'radio', 'A1-2': 'antenna', 'A1-3': 'holder', 'A1-4': 'lead',
        'A2-1': 'gland', 'A2-2': 'vent', 'A2-3': 'gasket', 'A2-4': 'bracket',
        'A3-1': 'screw', 'A3-2': 'washer', 'A3-3': 'screw_b',
    }
    levels = {
        'A1-1': (20, 60), 'A1-2': (20, 60), 'A1-3': (20, 60), 'A1-4': (40, 120),
        'A2-1': (20, 80), 'A2-2': (50, 200), 'A2-3': (40, 120), 'A2-4': (6, 20),
        'A3-1': (500, 2000), 'A3-2': (500, 2000), 'A3-3': (200, 800),
    }

    def shelf_bin(code):
        low, high = levels.get(code, (None, None))
        key = single.get(code)

        return bin_(p[key] if key else None, shelf_bins[code], low=low, high=high, label='' if key else code)

    api.put(f'/plugin/virtual-bins/unit/{shelving}/layout/', {'layout': {
        'kind': 'shelving',
        'product': None,
        'rows': [
            {'name': f'Shelf {row}', 'columns': [
                {'bins': [shelf_bin(f'A{row}-{column}')]} for column in (1, 2, 3, 4)
            ]}
            for row in (1, 2, 3)
        ],
    }})

    print('Demo data created.')
    print(f'  Assembly bench: {base}/web/stock/location/{bench}/')
    print(f'  Packing bench:  {base}/web/stock/location/{packing}/')
    print(f'  Shelving unit:  {base}/web/stock/location/{shelving}/')
    print(f'  All units:      {base}/web/plugin/virtual-bins/units')


if __name__ == '__main__':
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)

    main(sys.argv[1], sys.argv[2])
