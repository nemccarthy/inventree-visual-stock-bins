import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Anchor, Badge, Loader, Select } from '@mantine/core';
import { type ReactNode, useEffect, useRef, useState } from 'react';

import { STATUS_COLOR, STATUS_LABEL } from './format';
import type { BinStatus } from './types';

const STYLE_ID = 'vb-styles';

const CSS = `
.vb-bin {
  appearance: none; border: 0; padding: 0; margin: 0; background: none; font: inherit; color: inherit;
  display: flex; flex-direction: column; cursor: pointer; border-radius: 6px; position: relative;
  text-align: left; flex: none;
}
.vb-bin:focus-visible { outline: 2px solid var(--mantine-primary-color-filled); outline-offset: 2px; }
.vb-bin[data-static='true'] { cursor: default; }
.vb-body {
  position: relative; overflow: hidden; box-sizing: border-box;
  border: 1px solid var(--mantine-color-default-border); border-bottom: 0;
  border-radius: 6px 6px 0 0; background: var(--mantine-color-default-hover);
}
.vb-bin:not([data-static='true']):hover .vb-body { border-color: var(--mantine-color-dimmed); }
.vb-level { position: absolute; left: 0; right: 0; bottom: 0; opacity: 0.3; transition: height 0.4s ease; }
.vb-content {
  position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center;
  justify-content: center; line-height: 1.15; padding: 2px 4px; text-align: center;
}
.vb-qty { font-weight: 700; font-variant-numeric: tabular-nums; white-space: nowrap; }
.vb-sub { color: var(--mantine-color-dimmed); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
.vb-mark { position: absolute; top: 3px; right: 4px; display: flex; gap: 2px; }
.vb-thumb { position: absolute; top: 4px; left: 4px; border-radius: 3px; object-fit: cover; background: var(--mantine-color-body); }
.vb-label {
  box-sizing: border-box; border: 1px solid var(--mantine-color-default-border); border-radius: 0 0 6px 6px;
  background: var(--mantine-color-body); padding: 3px 5px; overflow: hidden; line-height: 1.2;
  font-weight: 500;
}
.vb-clamp { display: -webkit-box; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
.vb-bin[data-status='low'] .vb-body { border-color: var(--mantine-color-yellow-outline); }
.vb-bin[data-status='low'] .vb-label { border-color: var(--mantine-color-yellow-outline); }
.vb-bin[data-status='empty'] .vb-body { border-style: dashed; border-color: var(--mantine-color-red-outline); background: var(--mantine-color-red-light); }
.vb-bin[data-status='empty'] .vb-label { border-color: var(--mantine-color-red-outline); }
.vb-bin[data-status='empty'] .vb-qty { color: var(--mantine-color-red-text); }
.vb-bin[data-status='unassigned'] .vb-body { border-style: dashed; background: transparent; }
.vb-bin[data-status='unassigned'] .vb-label { border-style: dashed; color: var(--mantine-color-dimmed); }
.vb-bin[data-selected='true'] { outline: 2px solid var(--mantine-primary-color-filled); outline-offset: 2px; }
.vb-bin[data-dim='true'] { opacity: 0.35; }
.vb-bin[data-flash='true'] { animation: vb-flash 1s ease-in-out infinite; z-index: 2; }
@keyframes vb-flash {
  0%, 100% { box-shadow: 0 0 0 2px var(--mantine-color-blue-filled), 0 0 0 0 var(--mantine-color-blue-light-hover); }
  50% { box-shadow: 0 0 0 3px var(--mantine-color-blue-filled), 0 0 0 12px var(--mantine-color-blue-light-hover); }
}
.vb-unit[data-flash='true'] { animation: vb-flash 1s ease-in-out infinite; border-radius: 8px; }
.vb-row { display: flex; align-items: flex-end; }
.vb-col { display: flex; flex-direction: column; align-items: center; flex: none; }
.vb-top { border-radius: 2px; background: var(--mantine-color-dimmed); opacity: 0.55; }
.vb-leg { width: 8px; height: 12px; background: var(--mantine-color-dimmed); opacity: 0.4; border-radius: 0 0 2px 2px; }
.vb-upright { width: 6px; background: var(--mantine-color-dimmed); opacity: 0.4; border-radius: 2px; flex: none; }
.vb-rowname { color: var(--mantine-color-dimmed); font-weight: 600; text-transform: uppercase; letter-spacing: 0.04em; }
.vb-bin[draggable='true'] { cursor: grab; }
.vb-bin[data-dragging='true'] { opacity: 0.3; }
.vb-gap { flex: none; align-self: stretch; border-radius: 4px; transition: background 0.1s; position: relative; }
.vb-gap[data-over='true'] { background: var(--mantine-primary-color-filled); }
.vb-gap[data-active='true']::after {
  content: ''; position: absolute; top: 15%; bottom: 15%; left: 50%; width: 0;
  border-left: 2px dashed var(--mantine-color-default-border);
}
.vb-gap[data-over='true']::after { display: none; }
.vb-slot { height: 6px; border-radius: 3px; width: 100%; transition: background 0.1s; }
.vb-slot[data-active='true'] { background: var(--mantine-color-default-border); }
.vb-slot[data-over='true'] { background: var(--mantine-primary-color-filled); height: 10px; }
.vb-add {
  appearance: none; font: inherit; color: var(--mantine-color-dimmed); cursor: pointer; flex: none;
  border: 1px dashed var(--mantine-color-default-border); border-radius: 6px; background: transparent;
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
}
.vb-add:hover { color: var(--mantine-color-text); border-color: var(--mantine-color-dimmed); }
.vb-full {
  position: fixed; inset: 0; z-index: 250; overflow: auto; background: var(--mantine-color-body);
  padding: 16px 20px 24px; box-sizing: border-box;
}
.vb-card {
  appearance: none; font: inherit; color: inherit; text-align: left; cursor: pointer; width: 100%;
  border: 1px solid var(--mantine-color-default-border); border-radius: 8px; padding: 14px 16px;
  background: var(--mantine-color-body); display: flex; flex-direction: column; align-items: stretch;
  justify-content: flex-start; height: 100%;
}
.vb-card:hover { border-color: var(--mantine-color-dimmed); background: var(--mantine-color-default-hover); }
.vb-num input { font-size: 28px; height: 60px; text-align: center; font-weight: 700; font-variant-numeric: tabular-nums; }
`;

/** Add the plugin's stylesheet to the page, once */
export function useStyles() {
  useEffect(() => {
    if (document.getElementById(STYLE_ID)) {
      return;
    }

    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
  }, []);
}

export function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

/**
 * The width of an element, kept up to date as it is resized.
 *
 * Returns a callback ref: the element is often not rendered until data has
 * loaded or a dialog has opened, long after the component was mounted.
 */
export function useWidth<T extends HTMLElement>(): [(element: T | null) => void, number] {
  const [element, setElement] = useState<T | null>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    if (!element) {
      return;
    }

    setWidth(element.clientWidth);

    if (typeof ResizeObserver === 'undefined') {
      return;
    }

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        setWidth(Math.round(entry.contentRect.width));
      }
    });

    observer.observe(element);

    return () => observer.disconnect();
  }, [element]);

  return [setElement, width];
}

/** True while the browser tab is visible */
export function usePageVisible(): boolean {
  const [visible, setVisible] = useState(
    typeof document === 'undefined' ? true : document.visibilityState !== 'hidden'
  );

  useEffect(() => {
    const update = () => setVisible(document.visibilityState !== 'hidden');

    document.addEventListener('visibilitychange', update);

    return () => document.removeEventListener('visibilitychange', update);
  }, []);

  return visible;
}

/** A link which navigates inside the InvenTree single page app */
export function AppLink({
  context,
  to,
  children,
  title,
  size = 'sm'
}: Readonly<{
  context: InvenTreePluginContext;
  to: string;
  children: ReactNode;
  title?: string;
  size?: string;
}>) {
  return (
    <Anchor
      href={`/web${to}`}
      title={title}
      size={size}
      onClick={(event) => {
        // Let the browser handle ctrl / cmd / middle click (open in a new tab)
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) {
          return;
        }

        event.preventDefault();
        context.navigate(to);
      }}
    >
      {children}
    </Anchor>
  );
}

export function StatusBadge({ status }: Readonly<{ status: BinStatus }>) {
  return (
    <Badge color={STATUS_COLOR[status]} variant='light' radius='sm'>
      {STATUS_LABEL[status]}
    </Badge>
  );
}

export interface Choice {
  value: string;
  label: string;
}

/**
 * A select box which searches the InvenTree API as the user types.
 *
 * 'url' is a list endpoint; 'toChoice' turns one of its results into an option.
 */
export function RemoteSelect({
  context,
  url,
  params,
  toChoice,
  value,
  current,
  onChange,
  label,
  description,
  placeholder,
  clearable = true,
  disabled,
  error,
  size,
  suggest
}: Readonly<{
  context: InvenTreePluginContext;
  url: string;
  params?: Record<string, any>;
  toChoice: (row: any) => Choice;
  value: number | null;
  /** The label of the current value, so that it shows before anything is searched */
  current?: string | null;
  onChange: (value: number | null, row: any | null) => void;
  label?: ReactNode;
  description?: ReactNode;
  placeholder?: string;
  clearable?: boolean;
  disabled?: boolean;
  error?: ReactNode;
  size?: string;
  /** Searched for when the list is opened with nothing chosen and nothing typed */
  suggest?: string;
}>) {
  const api = useRef(context.api);
  api.current = context.api;

  const [search, setSearch] = useState('');
  const [rows, setRows] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [opened, setOpened] = useState(false);
  const term = useDebounced(search, 250);
  const paramsKey = JSON.stringify(params ?? {});

  useEffect(() => {
    if (!opened) {
      return;
    }

    let cancelled = false;

    setLoading(true);

    api.current
      .get(url, { params: { ...(params ?? {}), search: term, limit: 25 } })
      .then((response) => {
        if (cancelled) {
          return;
        }

        const data = response?.data;
        setRows(Array.isArray(data) ? data : Array.isArray(data?.results) ? data.results : []);
      })
      .catch(() => {
        if (!cancelled) {
          setRows([]);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, paramsKey, term, opened]);

  const choices = rows.map(toChoice);

  if (value !== null && !choices.some((choice) => choice.value === String(value))) {
    choices.unshift({ value: String(value), label: current || `#${value}` });
  }

  return (
    <Select
      label={label}
      description={description}
      placeholder={placeholder ?? 'Type to search'}
      size={size}
      searchable
      clearable={clearable}
      disabled={disabled}
      error={error}
      data={choices}
      value={value === null ? null : String(value)}
      // The server has already filtered the list
      filter={({ options }) => options}
      searchValue={search}
      onSearchChange={setSearch}
      onDropdownOpen={() => {
        if (value === null && !search && suggest) {
          setSearch(suggest);
        }

        setOpened(true);
      }}
      onDropdownClose={() => setOpened(false)}
      onChange={(next) => {
        if (next === null) {
          onChange(null, null);
          return;
        }

        const row = rows.find((candidate) => toChoice(candidate).value === next) ?? null;
        onChange(Number(next), row);
      }}
      nothingFoundMessage={loading ? 'Searching…' : 'Nothing found'}
      rightSection={loading ? <Loader size={14} /> : undefined}
      comboboxProps={{ withinPortal: true, zIndex: 400 }}
      maxDropdownHeight={280}
    />
  );
}

export function partChoice(row: any): Choice {
  return {
    value: String(row.pk),
    label: row.IPN ? `${row.full_name ?? row.name} (${row.IPN})` : (row.full_name ?? row.name)
  };
}

export function locationChoice(row: any): Choice {
  return { value: String(row.pk), label: row.pathstring ?? row.name };
}
