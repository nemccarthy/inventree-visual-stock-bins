"""Virtual Bins plugin for InvenTree.

Draws a stock location - a workbench, a shelving unit - the way it looks from
the front: every bin a tile showing what is in it. Bins can be counted, topped
up and emptied from the drawing.
"""

from plugin import InvenTreePlugin
from plugin.mixins import LocateMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin

from . import PLUGIN_VERSION

# Compiled frontend: a single file which exports every entry point
FRONTEND = 'VirtualBins.js'

ICON = 'ti:layout-grid:outline'


class VirtualBinsPlugin(
    LocateMixin, SettingsMixin, UrlsMixin, UserInterfaceMixin, InvenTreePlugin
):
    """A visual view of the bins in a stock location."""

    # Plugin metadata
    TITLE = 'Virtual Bins'
    NAME = 'VirtualBins'
    SLUG = 'virtual-bins'
    DESCRIPTION = 'See, count and refill the bins of a bench or shelving unit as a drawing'
    VERSION = PLUGIN_VERSION

    AUTHOR = 'EdgeMachines'
    WEBSITE = 'https://github.com/nemccarthy/inventree-visual-stock-bins'
    LICENSE = 'MIT'

    # Developed and tested against InvenTree 1.7.3
    MIN_VERSION = '1.7.0'

    SETTINGS = {
        'REFRESH_SECONDS': {
            'name': 'Refresh every (seconds)',
            'description': 'How often an open view reloads the stock levels. 0 turns this off',
            'validator': int,
            'default': 30,
        },
        'LOCATE_SECONDS': {
            'name': 'Locate highlight (seconds)',
            'description': 'How long a bin flashes after "Locate" is pressed for a stock item or location',
            'validator': int,
            'default': 20,
        },
        'SHOW_IMAGES': {
            'name': 'Show part images',
            'description': 'Show the image of the part on medium and large bins',
            'validator': bool,
            'default': True,
        },
        'BLIND_COUNT': {
            'name': 'Blind counts',
            'description': 'Hide the quantity InvenTree expects while a bench is counted bin by bin',
            'validator': bool,
            'default': False,
        },
        'INCLUDE_OPTIONAL': {
            'name': 'Count optional BOM lines',
            'description': 'Include optional BOM lines when working out how many units a bin covers',
            'validator': bool,
            'default': False,
        },
        'SHOW_NAVIGATION': {
            'name': 'Show in the navigation bar',
            'description': 'Add a Bins link to the main navigation bar',
            'validator': bool,
            'default': True,
        },
        'SHOW_LOCATION_PANEL': {
            'name': 'Show on stock location pages',
            'description': 'Add a Bins panel to stock location pages',
            'validator': bool,
            'default': True,
        },
        'PANEL_CONFIGURED_ONLY': {
            'name': 'Only on locations with bins',
            'description': 'Only show the Bins panel on locations which have bins set up. New units are then started from the Bins page',
            'validator': bool,
            'default': False,
        },
    }

    # Custom URL endpoints (from UrlsMixin), served below /plugin/virtual-bins/
    def setup_urls(self):
        """Register the API endpoints."""
        from django.urls import path

        from . import views

        return [
            path('config/', views.ConfigView.as_view(), name='virtual-bins-config'),
            path('units/', views.UnitsView.as_view(), name='virtual-bins-units'),
            path('attention/', views.AttentionView.as_view(), name='virtual-bins-attention'),
            path('locate/', views.LocateView.as_view(), name='virtual-bins-locate'),
            path('unit/<int:pk>/', views.UnitView.as_view(), name='virtual-bins-unit'),
            path('unit/<int:pk>/layout/', views.LayoutView.as_view(), name='virtual-bins-layout'),
            path(
                'unit/<int:pk>/autofill/',
                views.AutofillView.as_view(),
                name='virtual-bins-autofill',
            ),
            path('unit/<int:pk>/refill/', views.RefillView.as_view(), name='virtual-bins-refill'),
            path('unit/<int:pk>/export/', views.ExportView.as_view(), name='virtual-bins-export'),
            path('unit/<int:pk>/import/', views.ImportView.as_view(), name='virtual-bins-import'),
            path(
                'unit/<int:pk>/bin/<str:bin_id>/sources/',
                views.SourcesView.as_view(),
                name='virtual-bins-sources',
            ),
            path(
                'unit/<int:pk>/bin/<str:bin_id>/adjust/',
                views.AdjustView.as_view(),
                name='virtual-bins-adjust',
            ),
        ]

    # Locating (from LocateMixin). InvenTree calls these from the background
    # worker when "Locate" is pressed; an open view picks the request up and
    # flashes the bin.

    def locate_stock_item(self, item_pk):
        """Flash the bin which holds a stock item."""
        from . import stock, store

        target = stock.locate_target(item_pk, None)

        if target:
            store.add_locate(**target)

    def locate_stock_location(self, location_pk):
        """Flash the bin, or the unit, which is a stock location."""
        from . import stock, store

        target = stock.locate_target(None, location_pk)

        if target:
            store.add_locate(**target)

    # User interface (from UserInterfaceMixin)

    @staticmethod
    def _can_view(request) -> bool:
        from users.permissions import check_user_role

        user = getattr(request, 'user', None)

        return bool(
            user
            and check_user_role(user, 'stock', 'view')
            and check_user_role(user, 'stock_location', 'view')
        )

    @staticmethod
    def _can_edit(request) -> bool:
        from users.permissions import check_user_role

        user = getattr(request, 'user', None)

        return bool(user and check_user_role(user, 'stock_location', 'change'))

    def get_ui_routes(self, request, context, **kwargs):
        """The Bins page, at /web/plugin/virtual-bins/units."""
        return [
            {
                'key': 'virtual-bins-units',
                'title': 'Virtual Bins',
                'source': self.plugin_static_file(f'{FRONTEND}:renderVirtualBinsPage'),
                'options': {'path': 'units'},
                'context': {'slug': self.SLUG},
            }
        ]

    def get_ui_navigation_items(self, request, context, **kwargs):
        """A link to the Bins page in the main navigation bar."""
        if not self.get_setting('SHOW_NAVIGATION') or not self._can_view(request):
            return []

        return [
            {
                'key': 'virtual-bins-units',
                'title': 'Bins',
                'icon': ICON,
                'options': {'url': f'plugin/{self.SLUG}/units'},
            }
        ]

    def get_ui_panels(self, request, context: dict, **kwargs):
        """Add the Bins panel to stock location pages."""
        context = context or {}

        if context.get('target_model') != 'stocklocation':
            return []

        if not self.get_setting('SHOW_LOCATION_PANEL') or not self._can_view(request):
            return []

        try:
            location_id = int(context.get('target_id'))
        except (TypeError, ValueError):
            return []

        from stock.models import StockLocation

        from . import store

        metadata = (
            StockLocation.objects.filter(pk=location_id).values_list('metadata', flat=True).first()
        )
        configured = isinstance(metadata, dict) and isinstance(metadata.get(store.META_KEY), dict)

        if not configured and (
            self.get_setting('PANEL_CONFIGURED_ONLY') or not self._can_edit(request)
        ):
            return []

        return [
            {
                'key': 'virtual-bins',
                'title': 'Bins',
                'description': 'The bins of this location, drawn as they are laid out',
                'icon': ICON,
                'source': self.plugin_static_file(f'{FRONTEND}:renderVirtualBinsLocationPanel'),
                'context': {'location_id': location_id, 'slug': self.SLUG},
            }
        ]

    def get_ui_dashboard_items(self, request, context, **kwargs):
        """A dashboard item listing the bins which are empty or low."""
        if not self._can_view(request):
            return []

        return [
            {
                'key': 'virtual-bins-attention',
                'title': 'Bins to refill',
                'description': 'Bins which are empty or below their minimum',
                'icon': ICON,
                'source': self.plugin_static_file(f'{FRONTEND}:renderVirtualBinsDashboardItem'),
                'context': {'slug': self.SLUG},
                'options': {'width': 4, 'height': 3},
            }
        ]
