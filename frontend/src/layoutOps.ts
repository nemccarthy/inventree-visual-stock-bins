import { cloneLayout, newBin, newId } from './format';
import type { Layout, LayoutBin, LayoutRow } from './types';

/**
 * Changes to a layout while it is edited. Every function returns a new
 * layout and leaves the one it was given alone.
 */

/** Where a bin is dropped */
export type Target =
  // As a new column of a row, before the given column (or at the end)
  | { type: 'column'; row: string; before: string | null }
  // Into the stack of a column, above the given bin (or at the bottom)
  | { type: 'stack'; column: string; before: string | null };

export interface Found {
  row: number;
  column: number;
  index: number;
  bin: LayoutBin;
}

export function locate(layout: Layout, id: string): Found | null {
  for (let r = 0; r < layout.rows.length; r++) {
    const columns = layout.rows[r].columns;

    for (let c = 0; c < columns.length; c++) {
      const index = columns[c].bins.findIndex((item) => item.id === id);

      if (index >= 0) {
        return { row: r, column: c, index, bin: columns[c].bins[index] };
      }
    }
  }

  return null;
}

function prune(layout: Layout): Layout {
  for (const row of layout.rows) {
    row.columns = row.columns.filter((column) => column.bins.length > 0);
  }

  return layout;
}

export function updateBin(layout: Layout, id: string, patch: Partial<LayoutBin>): Layout {
  const next = cloneLayout(layout);
  const found = locate(next, id);

  if (found) {
    Object.assign(found.bin, patch);
  }

  return next;
}

export function removeBin(layout: Layout, id: string): Layout {
  const next = cloneLayout(layout);
  const found = locate(next, id);

  if (found) {
    next.rows[found.row].columns[found.column].bins.splice(found.index, 1);
  }

  return prune(next);
}

function place(layout: Layout, item: LayoutBin, target: Target): boolean {
  if (target.type === 'column') {
    const row = layout.rows.find((candidate) => candidate.id === target.row);

    if (!row) {
      return false;
    }

    const column = { id: newId('c'), bins: [item] };
    const at = target.before
      ? row.columns.findIndex((candidate) => candidate.id === target.before)
      : -1;

    if (at >= 0) {
      row.columns.splice(at, 0, column);
    } else {
      row.columns.push(column);
    }

    return true;
  }

  for (const row of layout.rows) {
    const column = row.columns.find((candidate) => candidate.id === target.column);

    if (!column) {
      continue;
    }

    const at = target.before
      ? column.bins.findIndex((candidate) => candidate.id === target.before)
      : -1;

    if (at >= 0) {
      column.bins.splice(at, 0, item);
    } else {
      column.bins.push(item);
    }

    return true;
  }

  return false;
}

/** Add a bin to the layout */
export function insertBin(layout: Layout, item: LayoutBin, target: Target): Layout {
  const next = cloneLayout(layout);

  place(next, item, target);

  return next;
}

/** Move a bin to another place. Dropping a bin on itself changes nothing. */
export function moveBin(layout: Layout, id: string, target: Target): Layout {
  if (target.before === id) {
    return layout;
  }

  const next = cloneLayout(layout);
  const found = locate(next, id);

  if (!found) {
    return layout;
  }

  const from = next.rows[found.row].columns[found.column];

  // A bin which is alone in its column, dropped beside that column, stays put
  if (target.type === 'column' && from.bins.length === 1) {
    const row = next.rows[found.row];
    const after = row.columns[found.column + 1]?.id ?? null;

    if (row.id === target.row && (target.before === from.id || target.before === after)) {
      return layout;
    }
  }

  from.bins.splice(found.index, 1);

  if (!place(next, found.bin, target)) {
    return layout;
  }

  return prune(next);
}

export type Nudge = 'left' | 'right' | 'up' | 'down' | 'stack-left' | 'stack-right';

/** Which nudges are possible for a bin */
export function canNudge(layout: Layout, id: string): Record<Nudge, boolean> {
  const found = locate(layout, id);
  const none = {
    left: false,
    right: false,
    up: false,
    down: false,
    'stack-left': false,
    'stack-right': false
  };

  if (!found) {
    return none;
  }

  const row = layout.rows[found.row];
  const stack = row.columns[found.column].bins.length;
  const alone = stack === 1;

  return {
    // A stacked bin can always be pulled out to the side
    left: !alone || found.column > 0,
    right: !alone || found.column < row.columns.length - 1,
    up: found.index > 0,
    down: found.index < stack - 1,
    'stack-left': found.column > 0,
    'stack-right': found.column < row.columns.length - 1
  };
}

/** Move a bin one step, for people who cannot or would rather not drag */
export function nudgeBin(layout: Layout, id: string, direction: Nudge): Layout {
  if (!canNudge(layout, id)[direction]) {
    return layout;
  }

  const next = cloneLayout(layout);
  const found = locate(next, id);

  if (!found) {
    return layout;
  }

  const row = next.rows[found.row];
  const column = row.columns[found.column];
  const alone = column.bins.length === 1;

  switch (direction) {
    case 'up':
    case 'down': {
      const other = found.index + (direction === 'up' ? -1 : 1);
      [column.bins[found.index], column.bins[other]] = [column.bins[other], column.bins[found.index]];
      break;
    }

    case 'left':
    case 'right': {
      const step = direction === 'left' ? -1 : 1;

      if (alone) {
        const other = found.column + step;
        [row.columns[found.column], row.columns[other]] = [row.columns[other], row.columns[found.column]];
      } else {
        // Out of the stack, into a column of its own beside it
        column.bins.splice(found.index, 1);
        row.columns.splice(found.column + (step > 0 ? 1 : 0), 0, { id: newId('c'), bins: [found.bin] });
      }

      break;
    }

    case 'stack-left':
    case 'stack-right': {
      const neighbour = row.columns[found.column + (direction === 'stack-left' ? -1 : 1)];
      column.bins.splice(found.index, 1);
      neighbour.bins.unshift(found.bin);
      break;
    }
  }

  return prune(next);
}

export function duplicateBin(layout: Layout, id: string): { layout: Layout; id: string | null } {
  const next = cloneLayout(layout);
  const found = locate(next, id);

  if (!found) {
    return { layout, id: null };
  }

  const copy = newBin({ ...found.bin, id: newId('b') });
  const row = next.rows[found.row];

  row.columns.splice(found.column + 1, 0, { id: newId('c'), bins: [copy] });

  return { layout: next, id: copy.id };
}

export function addRow(layout: Layout): Layout {
  const next = cloneLayout(layout);

  next.rows.push({ id: newId('r'), name: '', columns: [] });

  return next;
}

export function removeRow(layout: Layout, id: string): Layout {
  const next = cloneLayout(layout);

  next.rows = next.rows.filter((row) => row.id !== id);

  if (next.rows.length === 0) {
    next.rows.push({ id: newId('r'), name: '', columns: [] });
  }

  return next;
}

export function updateRow(layout: Layout, id: string, patch: Partial<LayoutRow>): Layout {
  const next = cloneLayout(layout);
  const row = next.rows.find((candidate) => candidate.id === id);

  if (row) {
    Object.assign(row, patch);
  }

  return next;
}

export function moveRow(layout: Layout, id: string, step: -1 | 1): Layout {
  const next = cloneLayout(layout);
  const at = next.rows.findIndex((row) => row.id === id);
  const other = at + step;

  if (at < 0 || other < 0 || other >= next.rows.length) {
    return layout;
  }

  [next.rows[at], next.rows[other]] = [next.rows[other], next.rows[at]];

  return next;
}

/** Bins which show the same stock as another bin: same part and same location */
export function duplicateIds(layout: Layout): Set<string> {
  const groups = new Map<string, string[]>();

  for (const row of layout.rows) {
    for (const column of row.columns) {
      for (const item of column.bins) {
        if (item.part === null && item.location === null) {
          continue;
        }

        const key = `${item.part}:${item.location}`;
        groups.set(key, [...(groups.get(key) ?? []), item.id]);
      }
    }
  }

  const out = new Set<string>();

  for (const ids of groups.values()) {
    if (ids.length > 1) {
      ids.forEach((id) => out.add(id));
    }
  }

  return out;
}

export function countBins(layout: Layout): number {
  return layout.rows.reduce(
    (total, row) => total + row.columns.reduce((sum, column) => sum + column.bins.length, 0),
    0
  );
}
