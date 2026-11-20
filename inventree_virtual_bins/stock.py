"""Reads the stock of a unit from InvenTree, and changes it.

Everything which touches the database is here; the arithmetic is in layout.py.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Q, Sum

from rest_framework.exceptions import ValidationError

from . import layout as layouts
from . import store

STATE_KEY = store.STATE_KEY

# Stock items listed for one bin
MAX_ITEMS = 50
# Places a refill can come from, listed for one bin
MAX_SOURCES = 8
# Parts in one bill of materials
MAX_BOM_PARTS = 5000


def present_filter() -> Q:
    """Stock which is physically in its location.

    This is InvenTree's own "in stock" test without the check of the stock
    status: a quarantined or damaged item is still in the bin.
    """
    return Q(
        quantity__gt=0,
        sales_order=None,
        belongs_to=None,
        customer=None,
        consumed_by=None,
        is_building=False,
    )


def num(value) -> float:
    if value is None:
        return 0.0

    return float(value)


def available_codes() -> set:
    from stock.status_codes import StockStatusGroups

    return set(StockStatusGroups.AVAILABLE_CODES)


def status_label(code) -> str:
    from stock.status_codes import StockStatus

    try:
        return str(StockStatus.label(code))
    except Exception:
        return str(code)


def error_text(exc) -> str:
    """The message of a Django validation error, as one line."""
    if hasattr(exc, 'message_dict'):
        parts = []

        for messages in exc.message_dict.values():
            parts.extend(str(message) for message in messages)

        return ' '.join(parts)

    if hasattr(exc, 'messages'):
        return ' '.join(str(message) for message in exc.messages)

    return str(exc)


# Locations


class Tree:
    """The stock locations, for working out what is below what."""

    def __init__(self):
        from stock.models import StockLocation

        self.rows = {
            row['pk']: row
            for row in StockLocation.objects.values(
                'pk', 'name', 'pathstring', 'tree_id', 'lft', 'rght', 'structural', 'parent_id'
            )
        }
        self._below: dict[int, frozenset] = {}

    def get(self, pk: int | None) -> dict | None:
        return self.rows.get(pk) if pk is not None else None

    def below(self, pk: int) -> frozenset:
        """The location and everything under it."""
        if pk not in self._below:
            top = self.rows.get(pk)

            if top is None:
                self._below[pk] = frozenset()
            else:
                self._below[pk] = frozenset(
                    row['pk']
                    for row in self.rows.values()
                    if row['tree_id'] == top['tree_id']
                    and row['lft'] >= top['lft']
                    and row['rght'] <= top['rght']
                )

        return self._below[pk]

    def describe(self, pk: int | None) -> dict | None:
        row = self.get(pk)

        if row is None:
            return None

        return {
            'pk': row['pk'],
            'name': row['name'],
            'pathstring': row['pathstring'],
            'structural': row['structural'],
        }


def location_info(location) -> dict:
    return {
        'pk': location.pk,
        'name': location.name,
        'pathstring': location.pathstring,
        'description': location.description,
        'structural': location.structural,
        'external': getattr(location, 'external', False),
        'parent': location.parent_id,
    }


# Parts


def part_info(pks) -> dict[int, dict]:
    """Name, IPN, units and thumbnail of each part."""
    from part.models import Part

    out = {}

    for part in Part.objects.filter(pk__in=set(pks)).only(
        'pk', 'name', 'IPN', 'description', 'units', 'image', 'trackable', 'active',
        'virtual', 'assembly', 'revision',
    ):
        thumbnail = None

        if part.image:
            try:
                thumbnail = part.get_thumbnail_url()
            except Exception:
                thumbnail = None

        out[part.pk] = {
            'pk': part.pk,
            'name': part.name,
            'ipn': part.IPN or '',
            'description': part.description or '',
            'units': part.units or '',
            'thumbnail': thumbnail,
            'trackable': part.trackable,
            'active': part.active,
            'virtual': part.virtual,
            'assembly': part.assembly,
        }

    return out


# Bills of materials


def load_bom(root: int) -> dict[int, list[dict]]:
    """Read the BOM below a part, every level, in the order of the BOM.

    Lines which a variant inherits from its template parts are included.
    """
    from part.models import BomItem, Part

    has_pieces = any(field.name == 'piece_count' for field in BomItem._meta.get_fields())
    fields = ['pk', 'part_id', 'sub_part_id', 'quantity', 'consumable', 'optional', 'inherited']

    if has_pieces:
        fields.append('piece_count')

    bom: dict[int, list[dict]] = {}
    templates: dict[int, int | None] = {}
    seen: set[int] = set()
    pending = {root}

    def template_of(pk: int) -> int | None:
        if pk not in templates:
            templates[pk] = (
                Part.objects.filter(pk=pk).values_list('variant_of_id', flat=True).first()
            )

        return templates[pk]

    while pending and len(seen) < MAX_BOM_PARTS:
        batch = pending - seen
        seen |= batch
        pending = set()

        if not batch:
            break

        templates.update(
            Part.objects.filter(pk__in=batch).values_list('pk', 'variant_of_id')
        )

        inherit_from: dict[int, list[int]] = {}

        for pk in batch:
            ancestor = templates.get(pk)
            guard = 0

            while ancestor and guard < 20:
                inherit_from.setdefault(ancestor, []).append(pk)
                ancestor = template_of(ancestor)
                guard += 1

        lines = (
            BomItem.objects.filter(
                Q(part__in=batch) | Q(part__in=list(inherit_from), inherited=True)
            )
            .order_by('pk')
            .values(*fields)
        )

        for line in lines:
            targets = []

            if line['part_id'] in batch:
                targets.append(line['part_id'])

            if line['inherited']:
                targets.extend(inherit_from.get(line['part_id'], []))

            quantity = num(line['quantity'])

            if has_pieces and line.get('piece_count'):
                quantity *= float(line['piece_count'])

            entry = {
                'part': line['sub_part_id'],
                'quantity': quantity,
                'consumable': bool(line['consumable']),
                'optional': bool(line['optional']),
            }

            for target in targets:
                bom.setdefault(target, []).append(entry)

            if line['sub_part_id'] not in seen:
                pending.add(line['sub_part_id'])

    return bom


# State kept beside the layout: when each bin was last counted


def get_state(location) -> dict:
    metadata = location.metadata if isinstance(location.metadata, dict) else {}
    state = metadata.get(STATE_KEY)

    return state if isinstance(state, dict) else {}


def _save_count(location, layout: dict, bin_id: str, user, quantity: float) -> None:
    from django.utils import timezone

    from stock.models import StockLocation

    with transaction.atomic():
        row = (
            StockLocation.objects.select_for_update()
            .filter(pk=location.pk)
            .values_list('metadata', flat=True)
            .first()
        )

        metadata = dict(row) if isinstance(row, dict) else {}
        state = metadata.get(STATE_KEY)
        counted = state.get('counted') if isinstance(state, dict) else None

        if not isinstance(counted, dict):
            counted = {}

        # Forget the bins which are no longer part of the layout
        ids = {item['id'] for item in layouts.all_bins(layout)}
        counted = {key: value for key, value in counted.items() if key in ids}

        counted[bin_id] = {
            'at': timezone.now().isoformat(timespec='seconds'),
            'by': getattr(user, 'username', '') or '',
            'quantity': quantity,
        }

        metadata[STATE_KEY] = {'counted': counted}
        StockLocation.objects.filter(pk=location.pk).update(metadata=metadata)
        location.metadata = metadata


# Reading a unit


def _item_rows(location_ids, part_ids=None):
    from stock.models import StockItem

    query = StockItem.objects.filter(present_filter(), location__in=location_ids)

    if part_ids is not None:
        query = query.filter(part__in=part_ids)

    return query.order_by('pk').values(
        'pk', 'part_id', 'location_id', 'quantity', 'batch', 'serial', 'status', 'updated',
        'stocktake_date',
    )


def _item_out(row: dict, tree: Tree, ok_codes: set) -> dict:
    place = tree.get(row['location_id'])

    return {
        'pk': row['pk'],
        'part': row['part_id'],
        'quantity': num(row['quantity']),
        'batch': row['batch'] or '',
        'serial': row['serial'] or '',
        'status': row['status'],
        'status_label': status_label(row['status']),
        'available': row['status'] in ok_codes,
        'location': row['location_id'],
        'location_name': place['pathstring'] if place else '',
        'updated': row['updated'].isoformat() if row['updated'] else None,
    }


def bin_scope(item: dict, unit_pk: int) -> int:
    """The location whose stock a bin shows."""
    return item['location'] or unit_pk


def load_unit(
    location, layout: dict, *, include_optional: bool = False, tree: Tree | None = None
) -> dict:
    """Everything the interface needs to draw a unit."""
    from django.utils import timezone

    from stock.models import StockItem

    tree = tree or Tree()
    ok_codes = available_codes()
    bins = layouts.all_bins(layout)
    unit_ids = tree.below(location.pk)

    scopes = {item['id']: bin_scope(item, location.pk) for item in bins}
    wanted_locations = set(unit_ids)

    for scope in scopes.values():
        wanted_locations |= tree.below(scope)

    # Bins which show a whole location need every item in it; otherwise only
    # the stock of the parts which have a bin is read
    whole_locations = any(item['part'] is None and item['location'] for item in bins)
    only_parts = None if whole_locations else {item['part'] for item in bins if item['part']}

    if not wanted_locations or (only_parts is not None and not only_parts):
        rows = []
    else:
        rows = list(_item_rows(wanted_locations, only_parts))

    by_location: dict[int, list[dict]] = {}

    for row in rows:
        by_location.setdefault(row['location_id'], []).append(row)

    part_ids = {item['part'] for item in bins if item['part']}

    if layout.get('product'):
        part_ids.add(layout['product'])

    # Bins which show a whole location list the parts in it
    for item in bins:
        if item['part'] is None and item['location']:
            for place in tree.below(item['location']):
                for row in by_location.get(place, []):
                    part_ids.add(row['part_id'])

    parts = part_info(part_ids)

    # Stock of the same parts which is somewhere else, and can be used
    elsewhere: dict[int, float] = {}
    bound_parts = {item['part'] for item in bins if item['part']}

    if bound_parts:
        for row in (
            StockItem.objects.filter(StockItem.IN_STOCK_FILTER, part__in=bound_parts)
            .exclude(location__in=unit_ids)
            .values('part_id')
            .annotate(total=Sum('quantity'))
        ):
            elsewhere[row['part_id']] = num(row['total'])

    # How many of each part go into one finished unit
    per_unit: dict[int, float] = {}
    consumable: set[int] = set()
    product = parts.get(layout.get('product')) if layout.get('product') else None
    bom: dict[int, list[dict]] = {}

    if product:
        bom = load_bom(product['pk'])
        exploded = layouts.explode_bom(bom, product['pk'], include_optional=include_optional)
        per_unit = exploded['per_unit']
        consumable = exploded['consumable']

    counted = get_state(location).get('counted')
    counted = counted if isinstance(counted, dict) else {}
    duplicates = layouts.duplicate_bindings(layout)

    out: dict[str, dict] = {}
    # Available stock of each part which has a bin, by stock item
    part_items: dict[int, dict[int, float]] = {}

    for item in bins:
        scope = scopes[item['id']]
        scope_ids = tree.below(scope)
        bound = bool(item['part'] or item['location'])
        part = parts.get(item['part']) if item['part'] else None

        held = []

        if bound:
            for place in scope_ids:
                for row in by_location.get(place, []):
                    if item['part'] is None or row['part_id'] == item['part']:
                        held.append(row)

        held.sort(key=lambda row: row['pk'])

        if item['part']:
            found = part_items.setdefault(item['part'], {})

            for row in held:
                if row['status'] in ok_codes:
                    found[row['pk']] = num(row['quantity'])

        quantity = sum(num(row['quantity']) for row in held)
        available = sum(num(row['quantity']) for row in held if row['status'] in ok_codes)

        contents = []

        if item['part'] is None and item['location']:
            totals: dict[int, float] = {}

            for row in held:
                totals[row['part_id']] = totals.get(row['part_id'], 0.0) + num(row['quantity'])

            contents = sorted(
                (
                    {
                        'part': pk,
                        'name': parts[pk]['name'] if pk in parts else f'Part {pk}',
                        'ipn': parts[pk]['ipn'] if pk in parts else '',
                        'quantity': total,
                    }
                    for pk, total in totals.items()
                ),
                key=lambda entry: entry['name'].lower(),
            )

        own_location = tree.describe(item['location']) if item['location'] else None

        if item['label']:
            title = item['label']
        elif part:
            title = part['name']
        elif own_location:
            title = own_location['name']
        elif item['part']:
            title = 'Missing part'
        elif item['location']:
            title = 'Missing location'
        else:
            title = 'Unassigned'

        status = layouts.bin_status(quantity, item['min'], bound)
        each = per_unit.get(item['part']) if item['part'] else None

        out[item['id']] = {
            'id': item['id'],
            'title': title,
            'bound': bound,
            'part': part,
            'part_missing': bool(item['part'] and not part),
            'location': own_location,
            'location_missing': bool(item['location'] and not own_location),
            'scope': tree.describe(scope),
            'quantity': round(quantity, 6),
            'available': round(available, 6),
            'held_back': round(quantity - available, 6),
            'items': [_item_out(row, tree, ok_codes) for row in held[:MAX_ITEMS]],
            'item_count': len(held),
            'serialized': any(row['serial'] for row in held),
            'contents': contents,
            'status': status,
            'fill': layouts.fill_fraction(quantity, item['min'], item['max']),
            'refill': layouts.refill_quantity(quantity, item['min'], item['max']) if item['part'] else 0.0,
            'per_unit': each,
            'covers': layouts.coverage(available, each),
            'consumable': bool(item['part'] and item['part'] in consumable),
            'elsewhere': elsewhere.get(item['part'], 0.0) if item['part'] else 0.0,
            'counted': counted.get(item['id']),
            'duplicates': duplicates.get(item['id'], []),
            'position': layouts.bin_position(layout, item['id']),
        }

    # How many finished units can be made from what is in the bins. A stock
    # item which two bins both show (the same binding, or one bin's location
    # inside the other's) counts once.
    buildable = None

    if product:
        totals = {part_pk: sum(found.values()) for part_pk, found in part_items.items()}

        for item in bins:
            if item['part']:
                totals.setdefault(item['part'], 0.0)

        result = layouts.buildable_units(
            bom, product['pk'], totals, include_optional=include_optional
        )

        if result is not None:
            short = set(result['short'])
            buildable = {
                'units': result['units'],
                'limited_by': [item['id'] for item in bins if item['part'] in short],
            }

    return {
        'location': location_info(location),
        'layout': layout,
        'bins': out,
        'summary': layouts.summarise([data['status'] for data in out.values()]),
        'product': product,
        'buildable': buildable,
        'generated': timezone.now().isoformat(timespec='seconds'),
    }


def unit_summary(
    location, layout: dict, *, include_optional: bool = False, tree: Tree | None = None
) -> dict:
    """The headline of a unit, for the list of units."""
    data = load_unit(location, layout, include_optional=include_optional, tree=tree)

    return {
        'location': data['location'],
        'kind': layout['kind'],
        'summary': data['summary'],
        'product': data['product'],
        'buildable': data['buildable'],
        'attention': [
            {
                'id': item['id'],
                'title': item['title'],
                'status': item['status'],
                'quantity': item['quantity'],
                'min': layouts.find_bin(layout, item['id'])['min'],
                'units': item['part']['units'] if item['part'] else '',
                'refill': item['refill'],
                'elsewhere': item['elsewhere'],
                'position': item['position'],
            }
            for item in data['bins'].values()
            if item['status'] in ('empty', 'low')
        ],
    }


# Refills


def refill_sources(part_pk: int, exclude_ids, tree: Tree, limit: int = MAX_SOURCES) -> list[dict]:
    """Stock of a part which a bin could be topped up from, oldest first."""
    from stock.models import StockItem

    rows = (
        StockItem.objects.filter(StockItem.IN_STOCK_FILTER, part=part_pk)
        .filter(Q(serial=None) | Q(serial=''))
        .exclude(location__in=exclude_ids)
        .exclude(location=None)
        .order_by('pk')
        .values('pk', 'quantity', 'batch', 'location_id')[:limit]
    )

    out = []

    for row in rows:
        place = tree.get(row['location_id'])

        out.append({
            'pk': row['pk'],
            'quantity': num(row['quantity']),
            'batch': row['batch'] or '',
            'location': row['location_id'],
            'location_name': place['pathstring'] if place else '',
        })

    return out


def refill_list(location, layout: dict) -> dict:
    """The bins of a unit which are due a refill, and where the stock is."""
    data = load_unit(location, layout)
    tree = Tree()
    unit_ids = tree.below(location.pk)
    lines = []

    for _r, _c, _s, item in layouts.iter_bins(layout):
        info = data['bins'][item['id']]

        if not item['part'] or info['refill'] <= 0:
            continue

        scope_ids = tree.below(bin_scope(item, location.pk))
        sources = refill_sources(item['part'], scope_ids | unit_ids, tree)

        lines.append({
            'bin': item['id'],
            'title': info['title'],
            'position': info['position'],
            'part': info['part'],
            'status': info['status'],
            'quantity': info['quantity'],
            'min': item['min'],
            'max': item['max'],
            'refill': info['refill'],
            'elsewhere': info['elsewhere'],
            'serialized': info['serialized'],
            'sources': sources,
        })

    return {
        'location': data['location'],
        'lines': lines,
        'generated': data['generated'],
    }


# Changing stock


class BinStock:
    """The stock items of one bin, locked for a change."""

    def __init__(self, location, layout: dict, bin_id: str):
        from part.models import Part
        from stock.models import StockItem, StockLocation

        self.unit = location
        self.layout = layout
        self.bin = layouts.find_bin(layout, bin_id)

        if self.bin is None:
            raise ValidationError({'detail': 'This bin is no longer part of the layout'})

        if not self.bin['part']:
            raise ValidationError({
                'detail': 'This bin is not set to a part, so its stock is changed in InvenTree'
            })

        self.part = Part.objects.filter(pk=self.bin['part']).first()

        if self.part is None:
            raise ValidationError({'detail': 'The part of this bin no longer exists'})

        self.tree = Tree()
        scope_pk = bin_scope(self.bin, location.pk)
        self.scope = StockLocation.objects.filter(pk=scope_pk).first()

        if self.scope is None:
            raise ValidationError({'detail': 'The location of this bin no longer exists'})

        self.scope_ids = self.tree.below(scope_pk)

        self.items = list(
            StockItem.objects.select_for_update()
            .filter(present_filter(), location__in=self.scope_ids, part=self.part)
            .order_by('pk')
        )

    @property
    def total(self) -> float:
        return sum(num(item.quantity) for item in self.items)

    def plain(self) -> list[dict]:
        """The items as layout.py wants them. Items are used in the order they were created."""
        return [{'pk': item.pk, 'quantity': num(item.quantity), 'age': item.pk} for item in self.items]

    def by_pk(self) -> dict:
        return {item.pk: item for item in self.items}

    def no_serials(self):
        if any(item.serial for item in self.items):
            raise ValidationError({
                'detail': 'This bin holds serial-numbered stock, which is changed item by item in InvenTree'
            })

    def create(self, quantity: float, user, notes: str):
        from stock.models import StockItem

        if self.scope.structural:
            raise ValidationError({
                'detail': f'"{self.scope.name}" is a structural location, which cannot hold stock. '
                'Give the bin a location of its own.'
            })

        item = StockItem(part=self.part, location=self.scope, quantity=Decimal(str(quantity)))
        item.save(user=user, notes=notes)

        return item


def _quantity(value, *, allow_zero: bool = False) -> float:
    result = layouts.number(value)

    if result is None or (result == 0 and not allow_zero):
        raise ValidationError({
            'quantity': 'Enter a quantity of zero or more' if allow_zero else 'Enter a quantity above zero'
        })

    return result


def _check(result, what: str):
    """InvenTree's stock methods return False when they refuse a change."""
    if result is False:
        raise ValidationError({'detail': f'InvenTree did not accept the {what}'})


def adjust(location, layout: dict, bin_id: str, action: str, data: dict, user, can) -> dict:
    """Change the stock of a bin.

    action is one of 'count', 'add', 'remove', 'move' (out of the bin) and
    'refill' (into the bin, from stock elsewhere). 'can' says whether the user
    may add new stock items.

    Returns a short description of what was done.
    """
    from stock.models import StockItem, StockLocation

    notes = layouts._text(data.get('notes'), 200)
    where = location.name
    done: dict = {'action': action}

    try:
        with transaction.atomic():
            stock = BinStock(location, layout, bin_id)
            before = stock.total

            if action == 'count':
                counted = _quantity(data.get('quantity'), allow_zero=True)
                stock.no_serials()
                plan = layouts.plan_count(stock.plain(), counted)
                items = stock.by_pk()
                note = notes or f'Counted in the bins of {where}'

                for change in plan['set']:
                    _check(items[change['pk']].stocktake(change['quantity'], user, notes=note), 'count')

                if plan['create'] > 0:
                    if not can('add'):
                        raise ValidationError({
                            'detail': 'You do not have permission to add new stock, which this count needs'
                        })

                    item = stock.create(plan['create'], user, note)
                    item.stocktake(plan['create'], user, notes=note)

                _save_count(location, layout, bin_id, user, counted)
                done.update(before=before, after=counted)

            elif action == 'add':
                quantity = _quantity(data.get('quantity'))
                stock.no_serials()
                note = notes or f'Added to the bin in {where}'

                if stock.items:
                    _check(stock.items[-1].add_stock(quantity, user, notes=note), 'addition')
                else:
                    if not can('add'):
                        raise ValidationError({
                            'detail': 'You do not have permission to add new stock'
                        })

                    stock.create(quantity, user, note)

                done.update(before=before, after=before + quantity)

            elif action == 'remove':
                quantity = _quantity(data.get('quantity'))
                stock.no_serials()
                note = notes or f'Removed from the bin in {where}'
                items = stock.by_pk()

                try:
                    plan = layouts.plan_remove(stock.plain(), quantity)
                except ValueError as exc:
                    raise ValidationError({'quantity': f'{exc} (it holds {before:g})'})

                for change in plan:
                    _check(items[change['pk']].take_stock(change['quantity'], user, notes=note), 'removal')

                done.update(before=before, after=before - quantity)

            elif action == 'move':
                quantity = _quantity(data.get('quantity'))
                stock.no_serials()
                destination = StockLocation.objects.filter(
                    pk=layouts._pk(data.get('destination'))
                ).first()

                if destination is None:
                    raise ValidationError({'destination': 'Choose where the stock goes'})

                if destination.pk in stock.scope_ids:
                    raise ValidationError({'destination': 'That is the location of this bin'})

                if destination.structural:
                    raise ValidationError({
                        'destination': 'That is a structural location, which cannot hold stock'
                    })

                note = notes or f'Moved out of the bin in {where}'
                items = stock.by_pk()

                try:
                    plan = layouts.plan_remove(stock.plain(), quantity)
                except ValueError as exc:
                    raise ValidationError({'quantity': f'{exc} (it holds {before:g})'})

                for change in plan:
                    _check(
                        items[change['pk']].move(
                            destination, note, user, quantity=Decimal(str(change['quantity']))
                        ),
                        'move',
                    )

                done.update(before=before, after=before - quantity, destination=destination.pathstring)

            elif action == 'refill':
                quantity = _quantity(data.get('quantity'))

                if stock.scope.structural:
                    raise ValidationError({
                        'detail': f'"{stock.scope.name}" is a structural location, which cannot hold stock. '
                        'Give the bin a location of its own.'
                    })

                note = notes or f'Bin topped up in {where}'
                source_pk = layouts._pk(data.get('source'))
                elsewhere = (
                    StockItem.objects.select_for_update()
                    .filter(StockItem.IN_STOCK_FILTER, part=stock.part)
                    .filter(Q(serial=None) | Q(serial=''))
                    .exclude(location__in=stock.scope_ids)
                    .exclude(location=None)
                    .order_by('pk')
                )

                if source_pk:
                    sources = list(elsewhere.filter(pk=source_pk))

                    if not sources:
                        raise ValidationError({
                            'source': 'That stock is no longer available. Refresh the list and try again.'
                        })
                else:
                    sources = list(elsewhere)

                on_hand = sum(num(item.quantity) for item in sources)

                if quantity > on_hand + 1e-9:
                    raise ValidationError({
                        'quantity': f'Only {on_hand:g} is available'
                        + (' in that stock item' if source_pk else ' elsewhere')
                    })

                left = quantity
                used = []

                for item in sources:
                    if left <= 1e-9:
                        break

                    take = min(num(item.quantity), left)
                    used.append(item.location.pathstring if item.location else '')
                    _check(
                        item.move(stock.scope, note, user, quantity=Decimal(str(round(take, 6)))),
                        'move',
                    )
                    left = round(left - take, 6)

                done.update(before=before, after=before + quantity, sources=sorted(set(used)))

            else:
                raise ValidationError({'action': 'Unknown action'})

    except DjangoValidationError as exc:
        raise ValidationError({'detail': error_text(exc)})

    return done


# Generated layouts


def bins_from_stock(location) -> list[dict]:
    """One bin for each part which has stock in a location or below it."""
    tree = Tree()
    totals: dict[int, float] = {}

    for row in _item_rows(tree.below(location.pk)):
        totals[row['part_id']] = totals.get(row['part_id'], 0.0) + num(row['quantity'])

    parts = part_info(totals)

    return [
        {'part': pk}
        for pk in sorted(totals, key=lambda pk: (parts[pk]['name'].lower() if pk in parts else '', pk))
    ]


def bins_from_children(location) -> list[dict]:
    """One bin for each location directly below a location.

    A child which holds a single part gets that part as well, so that the bin
    can be counted and refilled.
    """
    from stock.models import StockLocation

    tree = Tree()
    out = []

    for child in StockLocation.objects.filter(parent=location).order_by('name'):
        held = {row['part_id'] for row in _item_rows(tree.below(child.pk))}

        out.append({'location': child.pk, 'part': held.pop() if len(held) == 1 else None})

    return out


def bins_from_bom(assembly_pk: int, *, all_levels: bool) -> list[dict]:
    """One bin for each part of a bill of materials, in the order of the BOM."""
    pks = layouts.bom_parts(load_bom(assembly_pk), assembly_pk, all_levels=all_levels)
    parts = part_info(pks)

    return [{'part': pk} for pk in pks if pk in parts and not parts[pk]['virtual']]


def check_references(layout: dict) -> None:
    """Make sure the parts and locations named in a layout exist."""
    from part.models import Part
    from stock.models import StockLocation

    bins = layouts.all_bins(layout)
    part_ids = {item['part'] for item in bins if item['part']}
    location_ids = {item['location'] for item in bins if item['location']}

    if layout.get('product'):
        product = Part.objects.filter(pk=layout['product']).values('assembly').first()

        if product is None:
            raise ValidationError({'product': 'The product no longer exists'})

        if not product['assembly']:
            raise ValidationError({'product': 'The product must be an assembly, with a BOM'})

    known_parts = dict(Part.objects.filter(pk__in=part_ids).values_list('pk', 'virtual'))
    missing = part_ids - set(known_parts)

    if missing:
        raise ValidationError({'detail': f'Part {sorted(missing)[0]} does not exist'})

    if any(known_parts.values()):
        raise ValidationError({'detail': 'A virtual part has no stock, so it cannot be kept in a bin'})

    known_locations = set(
        StockLocation.objects.filter(pk__in=location_ids).values_list('pk', flat=True)
    )
    missing = location_ids - known_locations

    if missing:
        raise ValidationError({'detail': f'Location {sorted(missing)[0]} does not exist'})


def locate_target(item_pk: int | None, location_pk: int | None) -> dict | None:
    """What a "locate" request points at: a location, and a part if it was a stock item."""
    from stock.models import StockItem, StockLocation

    if item_pk:
        row = StockItem.objects.filter(pk=item_pk).values('part_id', 'location_id').first()

        if row is None or row['location_id'] is None:
            return None

        return {'location': row['location_id'], 'part': row['part_id'], 'item': item_pk}

    if location_pk and StockLocation.objects.filter(pk=location_pk).exists():
        return {'location': location_pk, 'part': None, 'item': None}

    return None


def locate_matches(entries: list[dict], location, layout: dict, tree: Tree | None = None) -> list[dict]:
    """Which bins of a unit the recent "locate" requests point at.

    - a stock item: the bins of its part which show the location it is in. If
      its part has no bin, the bin which shows that location, or else the unit
    - a location inside the unit: the bins which are that location, or are in it
    - the location of the unit, or one above it: the unit as a whole
    """
    tree = tree or Tree()
    unit_ids = tree.below(location.pk)
    bins = layouts.all_bins(layout)
    out = []

    for entry in entries:
        target = entry.get('location')

        if target is None:
            continue

        hits: list[str] = []
        whole_unit = False

        if entry.get('part'):
            hits = [
                item['id']
                for item in bins
                if item['part'] == entry['part'] and target in tree.below(bin_scope(item, location.pk))
            ]

            if not hits:
                hits = [
                    item['id']
                    for item in bins
                    if item['part'] is None and item['location'] and target in tree.below(item['location'])
                ]

            whole_unit = not hits and target in unit_ids
        elif target == location.pk or location.pk in tree.below(target):
            whole_unit = True
        elif target in unit_ids:
            hits = [
                item['id']
                for item in bins
                if item['location']
                and (target in tree.below(item['location']) or item['location'] in tree.below(target))
            ]

        if hits or whole_unit:
            out.append({'bins': hits, 'unit': whole_unit, 'age': entry.get('age', 0), 'at': entry['at']})

    return out
