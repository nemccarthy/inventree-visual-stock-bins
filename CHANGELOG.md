# Changelog

All notable changes to this plugin are recorded here.
Versions follow [semantic versioning](https://semver.org).

## 0.2.0 - 2026-11-23

- Layout files: the editor downloads the layout of a unit as a JSON file and
  uploads one, into the same location or another. Parts are written by IPN and
  name and locations by path, so a file reads the same in another location or
  another InvenTree, and it is laid out to be edited by hand (one bin on a
  line). See "Layout files" in the README
- After an upload the editor lists the parts and locations it could not match.
  Those bins are kept as placeholders under their label, and the part search
  of such a bin starts from its label
- New API endpoints `unit/<location>/export/` and `unit/<location>/import/`
- Labels below the bins have two lines at every size. On a long bench the
  bins are narrow, and one line cut long names short
- Two example layout files in `examples/`

## 0.1.0 - 2026-11-21

First release. Built and tested against InvenTree 1.7.3.

- A drawing of the bins of a stock location, seen from the front: rows,
  columns and stacks, three bin sizes, drawn as a bench or as shelving
- Schematic layout editor with drag and drop, and buttons which do the same
  without dragging
- Bins made for you from the stock in a location, from the locations below it,
  or from the BOM of an assembly
- A bin shows a part in the unit's location, a part in a location of its own,
  or everything in a location
- Minimum and "fill to" levels per bin: empty, below minimum and the level in
  the bin
- Bin drawer with stock items, batches and statuses, and count, add, remove,
  move out and top up through InvenTree's own stock adjustments
- Count walk: a unit counted bin by bin in the order of its layout, with blind
  counts and a summary of the differences
- Refill list with where the stock is, a top-up button per bin and a pick list
  to copy
- Units covered: how many units of a product each bin is enough for, how many
  the unit can build (sub-assemblies taken into account) and which bin runs
  out first
- "Locate" in InvenTree flashes the bin on any open drawing
- Bins page, Bins panel on stock location pages, "Bins to refill" dashboard
  widget, full window mode with automatic refresh
- API under `/plugin/virtual-bins/`
- Installable straight from the git repository (the compiled frontend is committed)
