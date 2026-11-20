"""Where the plugin keeps its data.

Nothing here needs its own database tables:

- The layout of a unit is stored in the metadata of its stock location, under
  the key 'virtual_bins'.
- "Locate" requests are stored for a short while in the metadata of the
  plugin's own configuration record, so that the web server and the background
  worker (which are separate processes) see the same list.
"""

from __future__ import annotations

import time

from . import layout as layouts

SLUG = 'virtual-bins'
META_KEY = 'virtual_bins'
# When each bin was last counted, kept beside the layout
STATE_KEY = 'virtual_bins_state'

# Locate requests are forgotten after this long
LOCATE_KEEP_SECONDS = 300
LOCATE_MAX = 20


# Layouts


def get_layout(location) -> dict | None:
    """Return the layout stored on a stock location, or None."""
    metadata = location.metadata if isinstance(location.metadata, dict) else {}
    raw = metadata.get(META_KEY)

    if not isinstance(raw, dict):
        return None

    return layouts.clean_layout(raw)


def _write(location_pk: int, value: dict | None) -> None:
    from django.db import transaction

    from stock.models import StockLocation

    with transaction.atomic():
        row = (
            StockLocation.objects.select_for_update()
            .filter(pk=location_pk)
            .values_list('metadata', flat=True)
            .first()
        )

        metadata = dict(row) if isinstance(row, dict) else {}

        if value is None:
            metadata.pop(META_KEY, None)
            metadata.pop(STATE_KEY, None)
        else:
            metadata[META_KEY] = value

        # Update at the database level: saving a location rebuilds its path
        # and fires its signals, none of which is wanted here
        StockLocation.objects.filter(pk=location_pk).update(metadata=metadata)


def save_layout(location, layout: dict) -> dict:
    """Store a layout on a stock location. The layout must already be clean."""
    _write(location.pk, layout)
    location.metadata = {**(location.metadata or {}), META_KEY: layout}

    return layout


def delete_layout(location) -> None:
    _write(location.pk, None)

    if isinstance(location.metadata, dict):
        location.metadata.pop(META_KEY, None)
        location.metadata.pop(STATE_KEY, None)


def unit_locations():
    """The stock locations which have a layout."""
    from stock.models import StockLocation

    return StockLocation.objects.filter(metadata__has_key=META_KEY).order_by('pathstring')


# Locate requests


def _load_plugin_data() -> dict:
    from plugin.models import PluginConfig

    metadata = (
        PluginConfig.objects.filter(key=SLUG).values_list('metadata', flat=True).first()
    )

    data = (metadata or {}).get(META_KEY) if isinstance(metadata, dict) else None

    return data if isinstance(data, dict) else {}


def _recent(entries, now: float) -> list[dict]:
    out = []

    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue

        try:
            at = float(entry.get('at'))
        except (TypeError, ValueError):
            continue

        if now - at <= LOCATE_KEEP_SECONDS and at <= now + 60:
            out.append(entry)

    return out[-LOCATE_MAX:]


def add_locate(location: int | None, part: int | None = None, item: int | None = None) -> None:
    """Record that somebody asked where a location or a stock item is."""
    from django.db import transaction

    from plugin.models import PluginConfig

    now = time.time()

    with transaction.atomic():
        config = PluginConfig.objects.select_for_update().filter(key=SLUG).first()

        if config is None:
            return

        metadata = config.metadata if isinstance(config.metadata, dict) else {}
        data = metadata.get(META_KEY)

        if not isinstance(data, dict):
            data = {}

        entries = _recent(data.get('locate'), now)
        entries.append({'at': round(now, 3), 'location': location, 'part': part, 'item': item})

        data['locate'] = entries[-LOCATE_MAX:]
        metadata[META_KEY] = data

        # Update at the database level: saving the PluginConfig has side effects
        PluginConfig.objects.filter(pk=config.pk).update(metadata=metadata)


def get_locates(max_age: float) -> list[dict]:
    """Locate requests of the last 'max_age' seconds, oldest first."""
    now = time.time()

    return [
        {**entry, 'age': round(max(0.0, now - float(entry['at'])), 1)}
        for entry in _recent(_load_plugin_data().get('locate'), now)
        if now - float(entry['at']) <= max_age
    ]
