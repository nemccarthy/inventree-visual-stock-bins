"""API views for the Virtual Bins plugin.

All endpoints are served below /plugin/virtual-bins/ and accept session or
token authentication, so they can also be used from scripts.
"""

from __future__ import annotations

from rest_framework import permissions
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import PLUGIN_VERSION, store
from . import layout as layouts
from . import stock as stocks


def _plugin():
    from plugin.registry import registry

    plugin = registry.get_plugin(store.SLUG)

    if plugin is None:
        raise NotFound('The Virtual Bins plugin is not active')

    return plugin


def _can(user, role: str, permission: str) -> bool:
    from users.permissions import check_user_role

    return bool(user and check_user_role(user, role, permission))


def user_permissions(user) -> dict:
    """What the user may do with the bins."""
    return {
        'view': _can(user, 'stock', 'view') and _can(user, 'stock_location', 'view'),
        # The layout is stored on the stock location
        'layout': _can(user, 'stock_location', 'change'),
        # Counting, adding, removing and moving stock
        'adjust': _can(user, 'stock', 'change'),
        # A count or an addition to an empty bin makes a new stock item
        'add': _can(user, 'stock', 'add'),
    }


def _setting_int(plugin, key: str, default: int, low: int, high: int) -> int:
    try:
        value = int(plugin.get_setting(key))
    except (TypeError, ValueError):
        return default

    return max(low, min(high, value))


def interface_settings(plugin) -> dict:
    return {
        'refresh_seconds': _setting_int(plugin, 'REFRESH_SECONDS', 30, 0, 3600),
        'locate_seconds': _setting_int(plugin, 'LOCATE_SECONDS', 20, 5, 300),
        'show_images': bool(plugin.get_setting('SHOW_IMAGES')),
        'blind_count': bool(plugin.get_setting('BLIND_COUNT')),
    }


class BinsView(APIView):
    """Base class: every endpoint needs permission to view stock and locations."""

    permission_classes = [permissions.IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        """Check the role permissions before handling the request."""
        super().initial(request, *args, **kwargs)

        if not user_permissions(request.user)['view']:
            raise PermissionDenied()

    def require(self, request, name: str):
        """Raise an error unless the user has the named permission."""
        if not user_permissions(request.user).get(name):
            raise PermissionDenied()

    @staticmethod
    def location(pk: int):
        from stock.models import StockLocation

        location = StockLocation.objects.filter(pk=pk).first()

        if location is None:
            raise NotFound('No such stock location')

        return location

    def unit(self, pk: int):
        """Return the location and its layout, or 404 if it has none."""
        location = self.location(pk)
        layout = store.get_layout(location)

        if layout is None:
            raise NotFound('No bins have been set up for this location')

        return location, layout

    def payload(self, request, location, layout) -> dict:
        plugin = _plugin()

        return {
            'configured': True,
            **stocks.load_unit(
                location, layout, include_optional=bool(plugin.get_setting('INCLUDE_OPTIONAL'))
            ),
            'settings': interface_settings(plugin),
            'permissions': user_permissions(request.user),
        }


class ConfigView(BinsView):
    """GET /plugin/virtual-bins/config/ - version, settings and the user's permissions."""

    def get(self, request, *args, **kwargs):
        return Response({
            'version': PLUGIN_VERSION,
            'settings': interface_settings(_plugin()),
            'permissions': user_permissions(request.user),
            'limits': {
                'rows': layouts.MAX_ROWS,
                'columns': layouts.MAX_COLUMNS,
                'stack': layouts.MAX_STACK,
                'bins': layouts.MAX_BINS,
            },
        })


class UnitsView(BinsView):
    """GET /plugin/virtual-bins/units/ - every location which has bins set up."""

    def get(self, request, *args, **kwargs):
        plugin = _plugin()
        optional = bool(plugin.get_setting('INCLUDE_OPTIONAL'))
        tree = stocks.Tree()
        units = []

        for location in store.unit_locations():
            layout = store.get_layout(location)

            if layout is not None:
                units.append(
                    stocks.unit_summary(location, layout, include_optional=optional, tree=tree)
                )

        return Response({
            'units': units,
            'settings': interface_settings(plugin),
            'permissions': user_permissions(request.user),
        })


class UnitView(BinsView):
    """GET /plugin/virtual-bins/unit/<location id>/ - the bins of a location and their stock."""

    def get(self, request, pk: int, *args, **kwargs):
        location = self.location(pk)
        layout = store.get_layout(location)

        if layout is None:
            from stock.models import StockLocation

            return Response({
                'configured': False,
                'location': stocks.location_info(location),
                'setup': {
                    'parts': len(stocks.bins_from_stock(location)),
                    'children': StockLocation.objects.filter(parent=location).count(),
                },
                'settings': interface_settings(_plugin()),
                'permissions': user_permissions(request.user),
            })

        return Response(self.payload(request, location, layout))


class LayoutView(BinsView):
    """PUT / DELETE /plugin/virtual-bins/unit/<location id>/layout/ - the layout of a unit.

    PUT {"layout": {"kind": "bench", "product": 12, "rows": [{"name": "",
    "columns": [{"bins": [{"part": 31, "size": "s", "min": 20, "max": 80}]}]}]}}
    """

    def put(self, request, pk: int, *args, **kwargs):
        self.require(request, 'layout')
        location = self.location(pk)

        try:
            layout = layouts.clean_layout(request.data.get('layout'), strict=True)
        except layouts.LayoutError as exc:
            raise ValidationError({'detail': str(exc)})

        stocks.check_references(layout)
        store.save_layout(location, layout)

        return Response(self.payload(request, location, layout))

    def delete(self, request, pk: int, *args, **kwargs):
        self.require(request, 'layout')
        location = self.location(pk)
        store.delete_layout(location)

        return Response(status=204)


class AutofillView(BinsView):
    """POST /plugin/virtual-bins/unit/<location id>/autofill/ - suggest a layout.

    {"source": "stock" | "children" | "bom", "assembly": <part id>,
     "levels": "direct" | "all", "layout": <layout to add to>}

    Nothing is saved: the suggested layout is returned for editing.
    """

    def post(self, request, pk: int, *args, **kwargs):
        self.require(request, 'layout')
        location = self.location(pk)
        source = request.data.get('source')
        product = None

        if source == 'stock':
            bins = stocks.bins_from_stock(location)
        elif source == 'children':
            bins = stocks.bins_from_children(location)
        elif source == 'bom':
            from part.models import Part

            assembly = Part.objects.filter(pk=layouts._pk(request.data.get('assembly'))).first()

            if assembly is None:
                raise ValidationError({'assembly': 'Choose an assembly'})

            if not assembly.assembly:
                raise ValidationError({'assembly': 'That part is not an assembly, so it has no BOM'})

            bins = stocks.bins_from_bom(
                assembly.pk, all_levels=request.data.get('levels') == 'all'
            )
            product = assembly.pk
        else:
            raise ValidationError({'source': 'Unknown source'})

        base = request.data.get('layout')

        if isinstance(base, dict):
            base = layouts.clean_layout(base)

            if product and not base.get('product'):
                base['product'] = product

            layout = layouts.append_bins(base, bins)
            added = len(layouts.all_bins(layout)) - len(layouts.all_bins(base))
        else:
            layout = layouts.layout_from_bins(bins, product=product)
            added = len(layouts.all_bins(layout))

        part_ids = {item['part'] for item in layouts.all_bins(layout) if item['part']}
        location_ids = {item['location'] for item in layouts.all_bins(layout) if item['location']}
        tree = stocks.Tree()

        return Response({
            'layout': layout,
            'added': added,
            'found': len(bins),
            # Names for the editor to show
            'parts': stocks.part_info(part_ids),
            'locations': {pk: tree.describe(pk) for pk in location_ids if tree.get(pk)},
        })


class AdjustView(BinsView):
    """POST /plugin/virtual-bins/unit/<location id>/bin/<bin id>/adjust/ - change the stock of a bin.

    {"action": "count", "quantity": 42}
    {"action": "add", "quantity": 10}
    {"action": "remove", "quantity": 4}
    {"action": "move", "quantity": 4, "destination": <location id>}
    {"action": "refill", "quantity": 50, "source": <stock item id, optional>}

    All take an optional "notes". Returns what was done and the unit as it is now.
    """

    def post(self, request, pk: int, bin_id: str, *args, **kwargs):
        self.require(request, 'adjust')
        location, layout = self.unit(pk)
        user = request.user

        done = stocks.adjust(
            location,
            layout,
            bin_id,
            str(request.data.get('action') or ''),
            request.data,
            user,
            lambda name: user_permissions(user).get(name, False),
        )

        return Response({'done': done, 'unit': self.payload(request, location, layout)})


class SourcesView(BinsView):
    """GET /plugin/virtual-bins/unit/<location id>/bin/<bin id>/sources/ - stock a bin can be topped up from."""

    def get(self, request, pk: int, bin_id: str, *args, **kwargs):
        location, layout = self.unit(pk)
        item = layouts.find_bin(layout, bin_id)

        if item is None:
            raise NotFound('This bin is no longer part of the layout')

        if not item['part']:
            return Response({'sources': []})

        tree = stocks.Tree()
        exclude = tree.below(stocks.bin_scope(item, location.pk))

        return Response({'sources': stocks.refill_sources(item['part'], exclude, tree, limit=25)})


class RefillView(BinsView):
    """GET /plugin/virtual-bins/unit/<location id>/refill/ - the bins which are due a refill."""

    def get(self, request, pk: int, *args, **kwargs):
        location, layout = self.unit(pk)

        return Response({
            **stocks.refill_list(location, layout),
            'permissions': user_permissions(request.user),
        })


class AttentionView(BinsView):
    """GET /plugin/virtual-bins/attention/ - empty and low bins of every unit, for the dashboard."""

    def get(self, request, *args, **kwargs):
        rank = {'empty': 0, 'low': 1}
        tree = stocks.Tree()
        bins = []
        units = 0

        for location in store.unit_locations():
            layout = store.get_layout(location)

            if layout is None:
                continue

            units += 1
            summary = stocks.unit_summary(location, layout, tree=tree)

            for item in summary['attention']:
                bins.append({
                    **item,
                    'unit': summary['location']['pk'],
                    'unit_name': summary['location']['name'],
                })

        bins.sort(key=lambda item: (rank[item['status']], item['unit_name'], item['title']))

        return Response({
            'units': units,
            'empty': sum(1 for item in bins if item['status'] == 'empty'),
            'low': sum(1 for item in bins if item['status'] == 'low'),
            'bins': bins[:40],
        })


class LocateView(BinsView):
    """GET /plugin/virtual-bins/locate/?unit=<location id> - bins somebody has just asked to locate."""

    def get(self, request, *args, **kwargs):
        plugin = _plugin()
        seconds = interface_settings(plugin)['locate_seconds']
        entries = store.get_locates(seconds)
        unit_pk = layouts._pk(request.query_params.get('unit'))

        if not entries:
            return Response({'seconds': seconds, 'matches': [], 'units': []})

        tree = stocks.Tree()

        if unit_pk:
            location, layout = self.unit(unit_pk)

            return Response({
                'seconds': seconds,
                'matches': stocks.locate_matches(entries, location, layout, tree),
            })

        # Without a unit: which units have something to show
        units = []

        for location in store.unit_locations():
            layout = store.get_layout(location)

            if layout is not None and stocks.locate_matches(entries, location, layout, tree):
                units.append(location.pk)

        return Response({'seconds': seconds, 'matches': [], 'units': units})
