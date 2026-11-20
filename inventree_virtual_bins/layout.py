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
