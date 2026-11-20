import type { BinData, BinSize, Layout, LayoutBin, Summary } from './types';

export const SLUG = 'virtual-bins';

const NO_API =
  'The Virtual Bins API was not found. Turn on "Enable URL integration" in the InvenTree plugin settings, then restart the server.';

export function apiUrl(path: string): string {
  return `/plugin/${SLUG}/${path}`;
}

/**
 * The body of an API response. With "Enable URL integration" off, InvenTree
 * redirects the plugin's URLs to the web interface, so the request "succeeds"
 * with a page of HTML: check for a field the real response always has.
 */
export function apiData<T>(response: any, field: string): T {
  const data = response?.data;

  if (!data || typeof data !== 'object' || !(field in data)) {
    throw Object.assign(new Error(NO_API), { vbNoApi: true });
  }

  return data as T;
}

/** Turn an API error into a message for the user */
export function apiError(err: any, fallback: string): string {
  const status = err?.response?.status;
  const data = err?.response?.data;

  if (err?.vbNoApi || (status === 404 && typeof data !== 'object')) {
    return NO_API;
  }

  if (status === 403) {
    return 'You do not have permission to do this.';
  }

  if (data && typeof data === 'object') {
    const messages: string[] = [];

    for (const value of Object.values(data)) {
      if (Array.isArray(value)) {
        messages.push(...value.map(String));
      } else if (typeof value === 'string') {
        messages.push(value);
      }
    }

    if (messages.length > 0) {
      return messages.join(' ');
    }
  }

  return `${fallback}${err?.message ? `: ${err.message}` : ''}`;
}

export function fmtQty(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return '';
  }

  return value.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

/** A quantity short enough for a small bin: 1,250 stays, 12,500 becomes 12.5k */
export function fmtShort(value: number): string {
  const abs = Math.abs(value);

  if (abs >= 1_000_000) {
    return `${(value / 1_000_000).toLocaleString(undefined, { maximumFractionDigits: 1 })}M`;
  }

  if (abs >= 10_000) {
    return `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 })}k`;
  }

  return value.toLocaleString(undefined, { maximumFractionDigits: abs < 10 ? 2 : 1 });
}

export function plural(count: number, one: string, many?: string): string {
  return `${fmtQty(count)} ${count === 1 ? one : (many ?? `${one}s`)}`;
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) {
    return '';
  }

  const date = new Date(iso);

  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return date.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit'
  });
}

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) {
    return '';
  }

  const date = new Date(iso);

  if (Number.isNaN(date.getTime())) {
    return '';
  }

  return date.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** "today", "yesterday", "3 days ago", or the date */
export function fmtAgo(iso: string | null | undefined): string {
  if (!iso) {
    return '';
  }

  const date = new Date(iso);

  if (Number.isNaN(date.getTime())) {
    return '';
  }

  const start = (value: Date) =>
    new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
  const days = Math.round((start(new Date()) - start(date)) / 86400000);

  if (days <= 0) {
    return `today, ${fmtTime(iso)}`;
  }

  if (days === 1) {
    return `yesterday, ${fmtTime(iso)}`;
  }

  if (days < 30) {
    return `${days} days ago`;
  }

  return date.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
}

export function partUrl(pk: number): string {
  return `/part/${pk}/`;
}

export function locationUrl(pk: number): string {
  return `/stock/location/${pk}/`;
}

export function stockItemUrl(pk: number): string {
  return `/stock/item/${pk}/`;
}

export function unitUrl(pk?: number | null): string {
  return pk ? `/plugin/${SLUG}/units?unit=${pk}` : `/plugin/${SLUG}/units`;
}

export const STATUS_LABEL: Record<string, string> = {
  ok: 'OK',
  low: 'Below minimum',
  empty: 'Empty',
  unassigned: 'Unassigned'
};

export const STATUS_COLOR: Record<string, string> = {
  ok: 'teal',
  low: 'yellow',
  empty: 'red',
  unassigned: 'gray'
};

export function summaryText(summary: Summary): string {
  const parts: string[] = [];

  if (summary.empty > 0) {
    parts.push(`${summary.empty} empty`);
  }

  if (summary.low > 0) {
    parts.push(`${summary.low} below minimum`);
  }

  if (parts.length === 0) {
    return summary.bins === 0 ? 'No bins yet' : `All ${plural(summary.bins, 'bin')} OK`;
  }

  return parts.join(', ');
}

// Layout helpers

/** Width and body height of a bin, in units of the small bin's width */
export const SIZE: Record<BinSize, { w: number; h: number }> = {
  s: { w: 1, h: 0.62 },
  m: { w: 1.3, h: 0.8 },
  l: { w: 1.7, h: 1.02 }
};

export const SIZE_LABEL: Record<BinSize, string> = {
  s: 'Small',
  m: 'Medium',
  l: 'Large'
};

export function allBins(layout: Layout): LayoutBin[] {
  return layout.rows.flatMap((row) => row.columns.flatMap((column) => column.bins));
}

export function cloneLayout(layout: Layout): Layout {
  return JSON.parse(JSON.stringify(layout)) as Layout;
}

let counter = 0;

/** A short identifier for a new row, column or bin */
export function newId(prefix: string): string {
  counter += 1;

  const random =
    typeof crypto !== 'undefined' && 'getRandomValues' in crypto
      ? Array.from(crypto.getRandomValues(new Uint8Array(4)), (byte) =>
          byte.toString(16).padStart(2, '0')
        ).join('')
      : Math.random().toString(16).slice(2, 10).padEnd(8, '0');

  return `${prefix}${random}${counter.toString(36)}`.slice(0, 24);
}

export function newBin(values: Partial<LayoutBin> = {}): LayoutBin {
  return {
    id: newId('b'),
    part: null,
    location: null,
    label: '',
    size: 's',
    min: null,
    max: null,
    note: '',
    ...values
  };
}

/** The bins a count walks through: the ones which hold a part and can be counted as a quantity */
export function countable(layout: Layout, bins: Record<string, BinData>): LayoutBin[] {
  return allBins(layout).filter((item) => {
    const data = bins[item.id];

    return !!data && !!data.part && !data.serialized;
  });
}

export function unitLabel(units: string | undefined | null, quantity: number): string {
  if (!units) {
    return fmtQty(quantity);
  }

  return `${fmtQty(quantity)} ${units}`;
}
