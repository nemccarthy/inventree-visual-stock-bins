"""The layout of a unit, and the arithmetic of its bins.

Plain Python: nothing in this module imports Django or InvenTree, so it is
tested on its own.

A *unit* is a bench or a shelving unit, drawn from the front. It is made of
rows (the bays of a bench, or the shelves of a shelving unit), each row of
columns, and each column of bins stacked on top of each other:

    {
        "version": 1,
        "kind": "bench",
        "product": 12,
        "rows": [
            {
                "id": "r1",
                "name": "Left bay",
                "columns": [
                    {"id": "c1", "bins": [{"id": "b1", "part": 31, ...}]}
                ]
            }
        ]
    }

A bin shows the stock of one part (``part``), held in the location of the
unit or in a location of its own (``location``). A bin with a location and no
part shows everything in that location. A bin with neither is a placeholder.
"""

from __future__ import annotations

import math
import uuid
from typing import Iterator

VERSION = 1

KINDS = ('bench', 'shelving')
SIZES = ('s', 'm', 'l')

MAX_ROWS = 12
MAX_COLUMNS = 40
MAX_STACK = 8
MAX_BINS = 400
MAX_LABEL = 60
MAX_NOTE = 200
MAX_NAME = 60
MAX_QUANTITY = 1e9

# Bins per row when a layout is generated
AUTOFILL_COLUMNS = 10


class LayoutError(ValueError):
    """A layout which cannot be stored."""


def new_id(prefix: str, taken: set | None = None) -> str:
    """Return a short identifier which is not in 'taken'."""
    while True:
        candidate = f'{prefix}{uuid.uuid4().hex[:8]}'

        if taken is None or candidate not in taken:
            if taken is not None:
                taken.add(candidate)

            return candidate


def _text(value, limit: int) -> str:
    if value is None:
        return ''

    return ' '.join(str(value).split())[:limit]


def _pk(value) -> int | None:
    """A primary key: a positive whole number, or None."""
    if isinstance(value, bool) or value is None or value == '':
        return None

    try:
        number = int(value)
    except (TypeError, ValueError):
        return None

    if number <= 0 or (isinstance(value, float) and value != number):
        return None

    return number


def number(value) -> float | None:
    """A quantity: a finite number of zero or more, or None."""
    if isinstance(value, bool) or value is None or value == '':
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(result) or math.isinf(result) or result < 0 or result > MAX_QUANTITY:
        return None

    return result


def _ident(value, prefix: str, taken: set) -> str:
    """Keep a stored identifier if it is usable and not yet taken, else make one."""
    text = str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else ''

    if text and len(text) <= 24 and text not in taken and all(
        ch.isalnum() or ch in '-_' for ch in text
    ):
        taken.add(text)
        return text

    return new_id(prefix, taken)


def clean_bin(raw: dict, taken: set, *, strict: bool = False) -> dict:
    """Normalise one bin."""
    if not isinstance(raw, dict):
        raise LayoutError('A bin must be an object')

    size = raw.get('size')

    if size not in SIZES:
        if strict and size not in (None, ''):
            raise LayoutError(f"Bin size must be one of {', '.join(SIZES)}")

        size = 's'

    low = number(raw.get('min'))
    high = number(raw.get('max'))

    if strict:
        for key in ('min', 'max'):
            if raw.get(key) not in (None, '') and number(raw.get(key)) is None:
                raise LayoutError('Bin levels must be numbers of zero or more')

        for key in ('part', 'location'):
            if raw.get(key) not in (None, '') and _pk(raw.get(key)) is None:
                raise LayoutError(f'Bin {key} must be the number of a {key}')

        if low is not None and high is not None and high < low:
            raise LayoutError('The level a bin is filled to cannot be below its minimum')

    if low is not None and high is not None and high < low:
        high = None

    return {
        'id': _ident(raw.get('id'), 'b', taken),
        'part': _pk(raw.get('part')),
        'location': _pk(raw.get('location')),
        'label': _text(raw.get('label'), MAX_LABEL),
        'size': size,
        'min': low,
        'max': high,
        'note': _text(raw.get('note'), MAX_NOTE),
    }


def empty_layout(kind: str = 'bench') -> dict:
    """A layout with a single empty row."""
    return {
        'version': VERSION,
        'kind': kind if kind in KINDS else 'bench',
        'product': None,
        'rows': [{'id': new_id('r'), 'name': '', 'columns': []}],
    }


def clean_layout(raw, *, strict: bool = False) -> dict:
    """Normalise a layout.

    By default this is forgiving: anything which is not understood is dropped,
    so that a stored layout can always be shown. With strict=True (used when a
    layout is saved) a LayoutError is raised instead.
    """
    if not isinstance(raw, dict):
        if strict:
            raise LayoutError('The layout must be an object')

        return empty_layout()

    kind = raw.get('kind')

    if kind not in KINDS:
        if strict and kind not in (None, ''):
            raise LayoutError(f"Kind must be one of {', '.join(KINDS)}")

        kind = 'bench'

    if strict and raw.get('product') not in (None, '') and _pk(raw.get('product')) is None:
        raise LayoutError('Product must be the number of a part')

    rows_in = raw.get('rows')

    if not isinstance(rows_in, list):
        if strict:
            raise LayoutError('The layout has no rows')

        rows_in = []

    if strict and len(rows_in) > MAX_ROWS:
        raise LayoutError(f'A unit can have at most {MAX_ROWS} rows')

    taken: set = set()
    rows = []
    total = 0

    for raw_row in rows_in[:MAX_ROWS]:
        if not isinstance(raw_row, dict):
            if strict:
                raise LayoutError('A row must be an object')

            continue

        columns_in = raw_row.get('columns')

        if not isinstance(columns_in, list):
            if strict:
                raise LayoutError('A row must have a list of columns')

            columns_in = []

        if strict and len(columns_in) > MAX_COLUMNS:
            raise LayoutError(f'A row can have at most {MAX_COLUMNS} columns')

        columns = []

        for raw_column in columns_in[:MAX_COLUMNS]:
            if not isinstance(raw_column, dict):
                if strict:
                    raise LayoutError('A column must be an object')

                continue

            bins_in = raw_column.get('bins')

            if not isinstance(bins_in, list):
                if strict:
                    raise LayoutError('A column must have a list of bins')

                bins_in = []

            if strict and len(bins_in) > MAX_STACK:
                raise LayoutError(f'A stack can have at most {MAX_STACK} bins')

            bins = []

            for raw_bin in bins_in[:MAX_STACK]:
                try:
                    bins.append(clean_bin(raw_bin, taken, strict=strict))
                except LayoutError:
                    if strict:
                        raise

                    continue

            # A column without bins has no width, so it is not kept
            if not bins:
                continue

            total += len(bins)

            if total > MAX_BINS:
                if strict:
                    raise LayoutError(f'A unit can have at most {MAX_BINS} bins')

                bins = bins[: max(0, len(bins) - (total - MAX_BINS))]
                total = MAX_BINS

                if not bins:
                    break

            columns.append({'id': _ident(raw_column.get('id'), 'c', taken), 'bins': bins})

        rows.append({
            'id': _ident(raw_row.get('id'), 'r', taken),
            'name': _text(raw_row.get('name'), MAX_NAME),
            'columns': columns,
        })

    if not rows:
        rows = [{'id': new_id('r', taken), 'name': '', 'columns': []}]

    return {
        'version': VERSION,
        'kind': kind,
        'product': _pk(raw.get('product')),
        'rows': rows,
    }


def iter_bins(layout: dict) -> Iterator[tuple[int, int, int, dict]]:
    """Walk the bins in reading order: rows from the top, columns from the
    left, and each stack from the top.

    Yields (row index, column index, position in the stack, bin).
    """
    for r, row in enumerate(layout.get('rows') or []):
        for c, column in enumerate(row.get('columns') or []):
            for s, item in enumerate(column.get('bins') or []):
                yield r, c, s, item


def all_bins(layout: dict) -> list[dict]:
    return [item for _r, _c, _s, item in iter_bins(layout)]


def find_bin(layout: dict, bin_id: str) -> dict | None:
    for item in all_bins(layout):
        if item['id'] == bin_id:
            return item

    return None


def bin_position(layout: dict, bin_id: str) -> str:
    """Where a bin is, in words: "Left bay, column 3, 2nd from the top"."""
    rows = layout.get('rows') or []

    for r, c, s, item in iter_bins(layout):
        if item['id'] != bin_id:
            continue

        row = rows[r]
        parts = []

        if row.get('name'):
            parts.append(row['name'])
        elif len(rows) > 1:
            parts.append(f'Row {r + 1}')

        parts.append(f'column {c + 1}')

        stack = len(row['columns'][c]['bins'])

        if stack > 1:
            if s == 0:
                parts.append('top')
            elif s == stack - 1:
                parts.append('bottom')
            else:
                parts.append(f'{ordinal(s + 1)} from the top')

        return ', '.join(parts)

    return ''


def ordinal(value: int) -> str:
    if 10 <= value % 100 <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(value % 10, 'th')

    return f'{value}{suffix}'


def duplicate_bindings(layout: dict) -> dict[str, list[str]]:
    """Bins which show the same stock as another bin of the unit.

    Two bins bound to the same part and the same location (or both to the
    location of the unit) count the same stock twice. Returns, for each such
    bin, the ids of the others.
    """
    groups: dict[tuple, list[str]] = {}

    for item in all_bins(layout):
        if item['part'] is None and item['location'] is None:
            continue

        groups.setdefault((item['part'], item['location']), []).append(item['id'])

    out: dict[str, list[str]] = {}

    for ids in groups.values():
        if len(ids) > 1:
            for bin_id in ids:
                out[bin_id] = [other for other in ids if other != bin_id]

    return out


# Levels


def bin_status(quantity: float, low: float | None, bound: bool = True) -> str:
    """'unassigned', 'empty', 'low' or 'ok'."""
    if not bound:
        return 'unassigned'

    if quantity <= 0:
        return 'empty'

    if low is not None and quantity < low:
        return 'low'

    return 'ok'


def fill_fraction(quantity: float, low: float | None, high: float | None) -> float | None:
    """How full a bin is, from 0 to 1, or None if the bin has no levels.

    Measured against the level it is filled to; a bin which only has a minimum
    is drawn as if it holds twice that.
    """
    if high is not None and high > 0:
        full = high
    elif low is not None and low > 0:
        full = low * 2
    else:
        return None

    return round(max(0.0, min(1.0, quantity / full)), 3)


def refill_quantity(quantity: float, low: float | None, high: float | None) -> float:
    """How much to put in a bin which is due a refill.

    A bin is due when it is empty or below its minimum. It is topped up to the
    level it is filled to, or to its minimum if it has no such level. A bin
    with no levels at all is never due.
    """
    if low is None and high is None:
        return 0.0

    due = quantity <= 0 or (low is not None and quantity < low)

    if not due:
        return 0.0

    target = high if high is not None else low

    return max(0.0, round((target or 0.0) - quantity, 6))


def coverage(quantity: float, per_unit: float | None) -> int | None:
    """How many finished units the contents of a bin are enough for."""
    if per_unit is None or per_unit <= 0:
        return None

    return int(math.floor(quantity / per_unit + 1e-9))


# Stock adjustments
#
# A bin can hold several stock items of the same part (two batches, or a
# top-up which arrived as its own item), while people count and use the bin as
# one quantity. These functions spread a change over the items. Each item is a
# dict with at least 'pk', 'quantity' and 'age' (anything sortable; smaller is
# older).


def _oldest_first(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda item: (item.get('age') is None, item.get('age'), item['pk']))


def plan_count(items: list[dict], counted: float) -> dict:
    """Set the total of a bin to the counted quantity.

    Returns {'set': [{'pk', 'quantity'}], 'create': quantity}:

    - every item is listed, so that each is stamped as counted, even if its
      quantity does not change
    - a shortfall is taken from the oldest items first (they are used first)
    - a surplus is added to the newest item
    - 'create' is the quantity of a new item, when the bin holds none
    """
    if counted < 0:
        raise ValueError('A count cannot be negative')

    ordered = _oldest_first(items)

    if not ordered:
        return {'set': [], 'create': counted if counted > 0 else 0.0}

    total = sum(item['quantity'] for item in ordered)
    result = {item['pk']: item['quantity'] for item in ordered}

    if counted > total:
        newest = ordered[-1]['pk']
        result[newest] = round(result[newest] + (counted - total), 6)
    elif counted < total:
        short = total - counted

        for item in ordered:
            take = min(item['quantity'], short)
            result[item['pk']] = round(item['quantity'] - take, 6)
            short = round(short - take, 6)

            if short <= 0:
                break

    return {
        'set': [{'pk': item['pk'], 'quantity': result[item['pk']]} for item in ordered],
        'create': 0.0,
    }


def plan_remove(items: list[dict], quantity: float) -> list[dict]:
    """Take a quantity out of a bin, oldest stock first.

    Returns [{'pk', 'quantity'}] - how much to take from each item. Raises
    ValueError if the bin does not hold that much.
    """
    if quantity <= 0:
        raise ValueError('The quantity must be more than zero')

    ordered = _oldest_first(items)
    total = sum(item['quantity'] for item in ordered)

    if quantity > total + 1e-9:
        raise ValueError('The bin does not hold that much')

    left = quantity
    out = []

    for item in ordered:
        if left <= 1e-9:
            break

        take = min(item['quantity'], left)

        if take > 0:
            out.append({'pk': item['pk'], 'quantity': round(take, 6)})
            left = round(left - take, 6)

    return out


# Bills of materials


def explode_bom(
    bom: dict[int, list[dict]],
    root: int,
    *,
    include_optional: bool = False,
    max_depth: int = 12,
) -> dict:
    """Work out how many of each part go into one unit of 'root'.

    'bom' maps a part to its BOM lines: [{'part', 'quantity', 'consumable',
    'optional'}]. Every level is included, so a sub-assembly which is kept in
    a bin gets a quantity as well as the parts inside it.

    Returns {'per_unit': {part: quantity}, 'consumable': set, 'loops': set}.
    Parts which are only ever used as consumables are listed in 'consumable'
    and have no quantity.
    """
    per_unit: dict[int, float] = {}
    consumable: set[int] = set()
    loops: set[int] = set()

    def walk(part: int, multiple: float, path: tuple, depth: int):
        if depth >= max_depth:
            return

        for line in bom.get(part) or []:
            child = line['part']

            if child in path or child == part:
                loops.add(child)
                continue

            if line.get('optional') and not include_optional:
                continue

            if line.get('consumable'):
                consumable.add(child)
                continue

            quantity = multiple * float(line.get('quantity') or 0)

            if quantity <= 0:
                continue

            per_unit[child] = round(per_unit.get(child, 0.0) + quantity, 9)
            walk(child, quantity, path + (child,), depth + 1)

    walk(root, 1.0, (root,), 0)

    return {
        'per_unit': per_unit,
        'consumable': {part for part in consumable if part not in per_unit},
        'loops': loops,
    }


def buildable_units(
    bom: dict[int, list[dict]],
    root: int,
    stock: dict[int, float],
    *,
    include_optional: bool = False,
    max_depth: int = 12,
    ceiling: int = 1_000_000,
) -> dict | None:
    """How many units of 'root' can be made from the stock of a unit.

    'stock' holds the quantity of every part which has a bin in the unit.
    Unlike explode_bom this nets off sub-assemblies: ten battery packs on the
    bench are ten units, even when the bin of cells is empty. The rules:

    - a part with a bin is taken from its bin first
    - what is then still missing is made from its own BOM, but only if every
      part on that BOM has a bin too (or can be made the same way); otherwise
      the part is short
    - the product itself, and a sub-assembly without a bin, is always made
      from its BOM. Parts on it which have no bin, and nothing below them
      with a bin, are not this unit's concern and never limit the number
    - consumable lines are ignored, and so are optional lines by default

    Returns {'units': n, 'short': [parts which run out first]}, or None when
    nothing the product needs is kept in the unit.
    """

    def lines(part: int) -> list[dict]:
        return [
            line
            for line in bom.get(part) or []
            if not line.get('consumable')
            and (include_optional or not line.get('optional'))
            and float(line.get('quantity') or 0) > 0
        ]

    touches_memo: dict[int, bool] = {}
    can_make_memo: dict[int, bool] = {}

    def touches(part: int, path: tuple = ()) -> bool:
        """True if something below the part has a bin."""
        if part in touches_memo:
            return touches_memo[part]

        if part in path or len(path) >= max_depth:
            return False

        result = any(
            line['part'] in stock or touches(line['part'], path + (part,))
            for line in lines(part)
        )

        if not path:
            touches_memo[part] = result

        return result

    def can_make(part: int, path: tuple = ()) -> bool:
        """True if more of the part can be made from what is in the bins."""
        if part in can_make_memo:
            return can_make_memo[part]

        if part in path or len(path) >= max_depth:
            return False

        below = lines(part)
        result = bool(below) and all(
            line['part'] in stock or can_make(line['part'], path + (part,)) for line in below
        )

        if not path:
            can_make_memo[part] = result

        return result

    if not touches(root):
        return None

    def attempt(units: int) -> set:
        """Try to make the units. Returns the parts which ran short."""
        left = dict(stock)
        short: set[int] = set()

        def need(part: int, quantity: float, path: tuple):
            if quantity <= 1e-9 or part in path or len(path) > max_depth:
                return

            if part == root:
                pass
            elif part in left:
                take = min(left[part], quantity)
                left[part] = left[part] - take
                quantity -= take

                if quantity <= 1e-9:
                    return

                if not can_make(part):
                    short.add(part)
                    return
            elif not touches(part):
                return

            for line in lines(part):
                need(line['part'], quantity * float(line['quantity']), path + (part,))

        need(root, float(units), ())

        return short

    if attempt(1):
        return {'units': 0, 'short': sorted(attempt(1))}

    low, high = 1, 2

    while high < ceiling and not attempt(high):
        low, high = high, high * 2

    high = min(high, ceiling)

    # 'low' can be made; 'high' cannot, unless it is the ceiling
    while high - low > 1:
        middle = (low + high) // 2

        if attempt(middle):
            high = middle
        else:
            low = middle

    if not attempt(high):
        low = high

    return {'units': low, 'short': sorted(attempt(low + 1))}


def bom_parts(
    bom: dict[int, list[dict]], root: int, *, all_levels: bool, max_depth: int = 12
) -> list[int]:
    """The parts of a BOM in the order they are listed, each once.

    With all_levels the lines of every sub-assembly follow the sub-assembly.
    """
    seen: set[int] = set()
    out: list[int] = []

    def walk(part: int, path: tuple, depth: int):
        for line in bom.get(part) or []:
            child = line['part']

            if child in path or child == part:
                continue

            if child not in seen:
                seen.add(child)
                out.append(child)

            if all_levels and depth + 1 < max_depth:
                walk(child, path + (child,), depth + 1)

    walk(root, (root,), 0)

    return out


# Generated layouts


def layout_from_bins(
    bins: list[dict],
    *,
    kind: str = 'bench',
    product: int | None = None,
    per_row: int = AUTOFILL_COLUMNS,
) -> dict:
    """Lay out a list of bins, one per column, wrapping into rows."""
    per_row = max(1, min(MAX_COLUMNS, per_row))
    bins = bins[:MAX_BINS]
    rows = []

    for start in range(0, len(bins), per_row):
        if len(rows) >= MAX_ROWS:
            break

        rows.append({
            'name': '',
            'columns': [{'bins': [item]} for item in bins[start : start + per_row]],
        })

    return clean_layout({'kind': kind, 'product': product, 'rows': rows})


def append_bins(layout: dict, bins: list[dict], *, per_row: int = AUTOFILL_COLUMNS) -> dict:
    """Add bins to a layout as new rows below the existing ones.

    Bins which the layout already has are left out: a bin for a location which
    has one, and a bin for a part (with no location of its own) which has one
    anywhere in the layout.
    """
    have_parts = {item['part'] for item in all_bins(layout) if item['part']}
    have_locations = {item['location'] for item in all_bins(layout) if item['location']}
    fresh = []

    for item in bins:
        part = _pk(item.get('part'))
        location = _pk(item.get('location'))

        if location:
            if location in have_locations:
                continue

            have_locations.add(location)
        elif part:
            if part in have_parts:
                continue
        else:
            continue

        if part:
            have_parts.add(part)

        fresh.append(item)

    extra = layout_from_bins(fresh, per_row=per_row)['rows'] if fresh else []

    rows = [row for row in layout.get('rows') or [] if row.get('columns')]

    return clean_layout({**layout, 'rows': rows + extra})


def summarise(statuses: list[str]) -> dict:
    """Count the bins of a unit by status."""
    return {
        'bins': len(statuses),
        'ok': statuses.count('ok'),
        'low': statuses.count('low'),
        'empty': statuses.count('empty'),
        'unassigned': statuses.count('unassigned'),
    }


# Layout files
#
# A layout can be downloaded as a JSON file, edited by hand and uploaded into
# another location, or into another InvenTree. In the file a part is named by
# its IPN and name as well as its number, and a location by its path, so that
# the file still means something where the numbers are different.

FILE_FORMAT = 'inventree-virtual-bins'
FILE_VERSION = 1

# Longest text accepted for an IPN, a part name or a location path
MAX_REFERENCE = 250


def _same(a, b) -> bool:
    """Compare two texts the way a layout file is matched: ignoring case and outer spaces."""
    return str(a or '').strip().casefold() == str(b or '').strip().casefold()


def _fold(value) -> str:
    return str(value or '').strip().casefold()


def part_ref(value) -> dict | None:
    """Read how a layout file names a part.

    - a number: the part with that primary key
    - a text: the part with that IPN, or failing that with that name
    - an object: {"ipn": ..., "name": ..., "pk": ...}, any of the three

    Returns {'pk', 'ipn', 'name', 'text'} or None. Raises LayoutError for
    anything else.
    """
    if value is None or value == '' or value == {}:
        return None

    if isinstance(value, bool):
        raise LayoutError('A part must be a number, a text or an object')

    if isinstance(value, (int, float)):
        pk = _pk(value)

        if pk is None:
            raise LayoutError('A part number must be a positive whole number')

        return {'pk': pk, 'ipn': '', 'name': '', 'text': ''}

    if isinstance(value, str):
        text = _text(value, MAX_REFERENCE)

        return {'pk': None, 'ipn': '', 'name': '', 'text': text} if text else None

    if isinstance(value, dict):
        raw_pk = value.get('pk', value.get('id'))

        if raw_pk not in (None, '') and _pk(raw_pk) is None:
            raise LayoutError('A part number ("pk") must be a positive whole number')

        ref = {
            'pk': _pk(raw_pk),
            'ipn': _text(value.get('ipn', value.get('IPN')), MAX_REFERENCE),
            'name': _text(value.get('name'), MAX_REFERENCE),
            'text': '',
        }

        return ref if ref['pk'] or ref['ipn'] or ref['name'] else None

    raise LayoutError('A part must be a number, a text or an object')


def location_ref(value) -> dict | None:
    """Read how a layout file names a location.

    - a number: the location with that primary key
    - a text: the location with that path ("Stores/Shelf A/A1"), or a path
      below the unit when it starts with "./" ("./A1")
    - an object: {"path": ..., "pk": ...}

    Returns {'pk', 'path'} or None.
    """
    if value is None or value == '' or value == {}:
        return None

    if isinstance(value, bool):
        raise LayoutError('A location must be a number, a path or an object')

    if isinstance(value, (int, float)):
        pk = _pk(value)

        if pk is None:
            raise LayoutError('A location number must be a positive whole number')

        return {'pk': pk, 'path': ''}

    if isinstance(value, str):
        path = _text(value, MAX_REFERENCE)

        return {'pk': None, 'path': path} if path else None

    if isinstance(value, dict):
        raw_pk = value.get('pk', value.get('id'))

        if raw_pk not in (None, '') and _pk(raw_pk) is None:
            raise LayoutError('A location number ("pk") must be a positive whole number')

        ref = {'pk': _pk(raw_pk), 'path': _text(value.get('path'), MAX_REFERENCE)}

        return ref if ref['pk'] or ref['path'] else None

    raise LayoutError('A location must be a number, a path or an object')


def describe_ref(ref: dict | None) -> str:
    """A reference as a person would write it, for messages."""
    if not ref:
        return ''

    words = [ref.get('name') or ref.get('text') or ref.get('path') or '']

    if ref.get('ipn'):
        words.append(f"({ref['ipn']})" if words[0] else ref['ipn'])

    text = ' '.join(word for word in words if word)

    return text or f"number {ref.get('pk')}"


def absolute_path(path: str, unit_path: str) -> str:
    """Turn a path from a layout file into a full location path.

    "./A1" and "." are below the unit; anything else is a full path already.
    """
    path = path.strip()

    if path == '.':
        return unit_path

    if path.startswith('./'):
        rest = path[2:].strip('/')

        return f'{unit_path}/{rest}' if rest else unit_path

    return path.strip('/')


def relative_path(path: str, unit_path: str) -> str:
    """Write a location path for a layout file: "./A1" when it is below the unit."""
    if unit_path and path == unit_path:
        return '.'

    if unit_path and path.startswith(f'{unit_path}/'):
        return f'./{path[len(unit_path) + 1:]}'

    return path


def parse_layout_file(doc) -> dict:
    """Read a layout file into bins with references which are still to be matched.

    Accepts the file as it is downloaded, a file written by hand, and a layout
    as the API stores it (columns as {"bins": [...]}, parts as numbers).

    Returns {'name', 'kind', 'product', 'rows': [{'name', 'columns': [[bin]]}]}
    where a bin is {'id', 'label', 'part', 'location', 'size', 'min', 'max',
    'note'} and 'part' / 'location' / 'product' are references or None.

    Raises LayoutError, with a message which says where, for a file which
    cannot be used.
    """
    if not isinstance(doc, dict):
        raise LayoutError('This is not a layout file: it must be a JSON object')

    file_format = doc.get('format')

    if file_format not in (None, '') and file_format != FILE_FORMAT:
        raise LayoutError(f'This is not a Virtual Bins layout file (its format is "{file_format}")')

    version = doc.get('version')

    if version not in (None, ''):
        if isinstance(version, bool) or not isinstance(version, (int, float)):
            raise LayoutError('The version of the layout file must be a number')

        if version > FILE_VERSION:
            raise LayoutError(
                f'This layout file was made by a newer version of the plugin (file version {version:g})'
            )

    kind = doc.get('kind')

    if kind in (None, ''):
        kind = 'bench'
    elif kind not in KINDS:
        raise LayoutError(f'"kind" must be one of {", ".join(KINDS)}')

    try:
        product = part_ref(doc.get('product'))
    except LayoutError as exc:
        raise LayoutError(f'Product: {exc}')

    rows_in = doc.get('rows')

    if not isinstance(rows_in, list):
        raise LayoutError('The layout file has no "rows"')

    if len(rows_in) > MAX_ROWS:
        raise LayoutError(f'A unit can have at most {MAX_ROWS} rows')

    rows = []
    total = 0

    for r, raw_row in enumerate(rows_in, start=1):
        if isinstance(raw_row, list):
            # A row written as just its columns
            raw_row = {'columns': raw_row}

        if not isinstance(raw_row, dict):
            raise LayoutError(f'Row {r} must be an object')

        columns_in = raw_row.get('columns')

        if columns_in is None:
            columns_in = []

        if not isinstance(columns_in, list):
            raise LayoutError(f'Row {r}: "columns" must be a list')

        if len(columns_in) > MAX_COLUMNS:
            raise LayoutError(f'Row {r}: a row can have at most {MAX_COLUMNS} columns')

        columns = []

        for c, raw_column in enumerate(columns_in, start=1):
            where = f'Row {r}, column {c}'

            if isinstance(raw_column, dict) and 'bins' in raw_column:
                bins_in = raw_column.get('bins')
            elif isinstance(raw_column, dict):
                # A column of one bin, written without its list
                bins_in = [raw_column]
            else:
                bins_in = raw_column

            if not isinstance(bins_in, list):
                raise LayoutError(f'{where} must be a list of bins')

            if len(bins_in) > MAX_STACK:
                raise LayoutError(f'{where}: a stack can have at most {MAX_STACK} bins')

            bins = []

            for b, raw_bin in enumerate(bins_in, start=1):
                spot = f'{where}, bin {b}' if len(bins_in) > 1 else where

                if not isinstance(raw_bin, dict):
                    raise LayoutError(f'{spot} must be an object')

                size = raw_bin.get('size')

                if size in (None, ''):
                    size = 's'
                elif size not in SIZES:
                    raise LayoutError(f'{spot}: "size" must be one of {", ".join(SIZES)}')

                levels = {}

                for key in ('min', 'max'):
                    value = raw_bin.get(key)

                    if value in (None, ''):
                        levels[key] = None
                    elif number(value) is None:
                        raise LayoutError(f'{spot}: "{key}" must be a number of zero or more')
                    else:
                        levels[key] = number(value)

                if (
                    levels['min'] is not None
                    and levels['max'] is not None
                    and levels['max'] < levels['min']
                ):
                    raise LayoutError(f'{spot}: "max" cannot be below "min"')

                try:
                    part = part_ref(raw_bin.get('part'))
                    place = location_ref(raw_bin.get('location'))
                except LayoutError as exc:
                    raise LayoutError(f'{spot}: {exc}')

                raw_id = raw_bin.get('id')

                bins.append({
                    'id': raw_id if isinstance(raw_id, str) else None,
                    'label': _text(raw_bin.get('label'), MAX_LABEL),
                    'part': part,
                    'location': place,
                    'size': size,
                    'min': levels['min'],
                    'max': levels['max'],
                    'note': _text(raw_bin.get('note'), MAX_NOTE),
                })

            if not bins:
                continue

            total += len(bins)

            if total > MAX_BINS:
                raise LayoutError(f'A unit can have at most {MAX_BINS} bins')

            columns.append(bins)

        rows.append({'name': _text(raw_row.get('name'), MAX_NAME), 'columns': columns})

    return {
        'name': _text(doc.get('name'), MAX_REFERENCE),
        'kind': kind,
        'product': product,
        'rows': rows,
    }


def file_bins(parsed: dict) -> list[dict]:
    """Every bin of a parsed layout file, in reading order."""
    return [item for row in parsed['rows'] for column in row['columns'] for item in column]


def wanted(parsed: dict) -> dict:
    """What has to be looked up to match a parsed layout file.

    Returns {'part_pks', 'part_texts', 'location_pks', 'location_paths'}; the
    texts are folded for comparison, the paths are still as written.
    """
    part_pks: set = set()
    part_texts: set = set()
    location_pks: set = set()
    location_paths: set = set()

    refs = [item['part'] for item in file_bins(parsed)] + [parsed.get('product')]

    for ref in refs:
        if not ref:
            continue

        if ref['pk']:
            part_pks.add(ref['pk'])

        for key in ('ipn', 'name', 'text'):
            if ref[key]:
                part_texts.add(_fold(ref[key]))

    for item in file_bins(parsed):
        ref = item['location']

        if not ref:
            continue

        if ref['pk']:
            location_pks.add(ref['pk'])

        if ref['path']:
            location_paths.add(ref['path'])

    return {
        'part_pks': part_pks,
        'part_texts': part_texts,
        'location_pks': location_pks,
        'location_paths': location_paths,
    }


def match_part(ref: dict, parts: list[dict]) -> tuple[int | None, str]:
    """Find the part a reference means among the candidates.

    'parts' is a list of {'pk', 'ipn', 'name'}. Returns (pk, '') or
    (None, why not).

    - If the reference has a number, and the part with that number has the
      IPN or name the reference gives (or it gives neither), that is the part.
    - Otherwise the part is found by IPN, by name, or by both when both are
      given. A number which belongs to a different part is not trusted: in
      another InvenTree the numbers are different.
    - Two parts which fit equally are not guessed between, unless the number
      picks one of them.
    """
    by_pk = {part['pk']: part for part in parts}
    named = bool(ref['ipn'] or ref['name'] or ref['text'])

    if ref['pk'] and ref['pk'] in by_pk:
        part = by_pk[ref['pk']]

        if (
            not named
            or (ref['ipn'] and _same(part['ipn'], ref['ipn']))
            or (ref['name'] and _same(part['name'], ref['name']))
            or (ref['text'] and (_same(part['ipn'], ref['text']) or _same(part['name'], ref['text'])))
        ):
            return part['pk'], ''

    if not named:
        return None, 'there is no part with that number'

    if ref['text']:
        found = [part for part in parts if part['ipn'] and _same(part['ipn'], ref['text'])]

        if not found:
            found = [part for part in parts if _same(part['name'], ref['text'])]
    else:
        found = parts

        if ref['ipn']:
            found = [part for part in found if part['ipn'] and _same(part['ipn'], ref['ipn'])]

        if ref['name']:
            both = [part for part in found if _same(part['name'], ref['name'])]

            # The IPN decides when the name has changed since the file was made
            found = both if both or not ref['ipn'] else found

    if len(found) == 1:
        return found[0]['pk'], ''

    if len(found) > 1:
        if ref['pk'] and any(part['pk'] == ref['pk'] for part in found):
            return ref['pk'], ''

        return None, f'{len(found)} parts match'

    if ref['pk'] and ref['pk'] in by_pk:
        # Say what the number is here: often the part was only renamed
        return None, f'no such part (number {ref["pk"]} is "{by_pk[ref["pk"]]["name"]}" here)'

    return None, 'no such part'


def match_location(ref: dict, locations: list[dict], unit_path: str) -> tuple[int | None, str]:
    """Find the location a reference means. 'locations' is a list of {'pk', 'path'}."""
    by_pk = {place['pk']: place for place in locations}
    path = absolute_path(ref['path'], unit_path) if ref['path'] else ''

    if ref['pk'] and ref['pk'] in by_pk:
        if not path or _same(by_pk[ref['pk']]['path'], path):
            return ref['pk'], ''

    if not path:
        return None, 'there is no location with that number'

    found = [place for place in locations if _same(place['path'], path)]

    if len(found) == 1:
        return found[0]['pk'], ''

    if len(found) > 1:
        if ref['pk'] and any(place['pk'] == ref['pk'] for place in found):
            return ref['pk'], ''

        return None, f'{len(found)} locations match'

    return None, 'no such location'


def reuse_ids(layout: dict, previous: dict | None) -> dict:
    """Give the bins of a new layout the ids of the bins they replace.

    When a layout is downloaded, edited and uploaded into the unit it came
    from, a bin which still shows the same thing keeps its id, and with it the
    record of when it was last counted.
    """
    if not previous:
        return layout

    spare: dict[tuple, list[str]] = {}

    for item in all_bins(previous):
        spare.setdefault((item['part'], item['location'], item['label']), []).append(item['id'])

    taken: set = set()
    waiting = []

    for item in all_bins(layout):
        ids = spare.get((item['part'], item['location'], item['label']))

        if ids:
            item['id'] = ids.pop(0)
            taken.add(item['id'])
        else:
            waiting.append(item)

    for item in waiting:
        if item['id'] in taken:
            item['id'] = new_id('b', taken)
        else:
            taken.add(item['id'])

    return layout


def export_layout(
    layout: dict,
    *,
    name: str,
    parts: dict[int, dict],
    locations: dict[int, dict],
    unit_path: str,
) -> dict:
    """Describe a layout for a layout file.

    'parts' maps a part number to {'ipn', 'name'}, 'locations' a location
    number to {'path'}. A part or location which is not in them is written
    with its number only.
    """

    def part_out(pk):
        info = parts.get(pk) or {}
        out = {}

        if info.get('ipn'):
            out['ipn'] = info['ipn']

        if info.get('name'):
            out['name'] = info['name']

        out['pk'] = pk

        return out

    def bin_out(item):
        out = {}

        if item['label']:
            out['label'] = item['label']

        if item['part']:
            out['part'] = part_out(item['part'])

        if item['location']:
            info = locations.get(item['location']) or {}
            place = {}

            if info.get('path'):
                place['path'] = relative_path(info['path'], unit_path)

            place['pk'] = item['location']
            out['location'] = place

        out['size'] = item['size']

        for key in ('min', 'max'):
            if item[key] is not None:
                value = item[key]
                out[key] = int(value) if float(value).is_integer() else value

        if item['note']:
            out['note'] = item['note']

        return out

    return {
        'format': FILE_FORMAT,
        'version': FILE_VERSION,
        'name': name,
        'kind': layout['kind'],
        'product': part_out(layout['product']) if layout.get('product') else None,
        'rows': [
            {
                'name': row['name'],
                'columns': [[bin_out(item) for item in column['bins']] for column in row['columns']],
            }
            for row in layout['rows']
        ],
    }


def format_layout_file(doc: dict) -> str:
    """Write a layout file as JSON which is pleasant to edit: one bin on a line."""
    import json

    def text(value) -> str:
        return json.dumps(value, ensure_ascii=False)

    lines = ['{']

    for key in ('format', 'version', 'name', 'kind', 'product'):
        lines.append(f'  {text(key)}: {text(doc.get(key))},')

    lines.append('  "rows": [')

    rows = doc.get('rows') or []

    for r, row in enumerate(rows):
        lines.append('    {')
        lines.append(f'      "name": {text(row.get("name", ""))},')
        lines.append('      "columns": [')

        columns = row.get('columns') or []

        for c, column in enumerate(columns):
            end = ',' if c < len(columns) - 1 else ''

            if len(column) == 1:
                lines.append(f'        [{text(column[0])}]{end}')
            else:
                lines.append('        [')

                for b, item in enumerate(column):
                    comma = ',' if b < len(column) - 1 else ''
                    lines.append(f'          {text(item)}{comma}')

                lines.append(f'        ]{end}')

        lines.append('      ]')
        lines.append('    }' + (',' if r < len(rows) - 1 else ''))

    lines.append('  ]')
    lines.append('}')

    return '\n'.join(lines) + '\n'
