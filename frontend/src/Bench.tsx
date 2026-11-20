import { Tooltip } from '@mantine/core';
import {
  IconAlertTriangle,
  IconCircleX,
  IconCopy,
  IconFlag,
  IconHelpCircle
} from '@tabler/icons-react';
import type { CSSProperties, DragEvent, ReactNode } from 'react';

import { SIZE, STATUS_COLOR, STATUS_LABEL, fmtQty, fmtShort } from './format';
import type { BinData, BinSize, BinStatus, Layout, LayoutBin, UnitKind } from './types';

export const U_MIN = 54;
export const U_MAX = 104;
const GAP = 0.07;

/** How wide a row is, in units of the small bin's width */
export function rowUnits(columns: { bins: { size: BinSize }[] }[], extra = 0): number {
  const widths = columns.map((column) =>
    Math.max(0, ...column.bins.map((item) => SIZE[item.size].w))
  );

  return widths.reduce((total, width) => total + width, 0) + GAP * Math.max(0, widths.length - 1) + extra;
}

/** The width of the widest row, in units of the small bin's width */
export function widestRow(layout: Layout, extra = 0): number {
  return Math.max(1, ...layout.rows.map((row) => rowUnits(row.columns, extra)));
}

/** The size of the small bin, in pixels, at which the widest row fits the space */
export function fitUnit(layout: Layout, width: number, extra = 0, chrome = 0): number {
  const widest = widestRow(layout, extra);

  if (width <= 0) {
    return 84;
  }

  return Math.max(U_MIN, Math.min(U_MAX, Math.floor(((width - chrome) / widest) * 10) / 10));
}

export function gapPx(u: number): number {
  return Math.max(4, Math.round(u * GAP));
}

export interface TileProps {
  title: string;
  size: BinSize;
  u: number;
  status: BinStatus;
  /** The large text in the bin */
  primary?: string;
  /** The small text below it */
  secondary?: string;
  fill?: number | null;
  thumbnail?: string | null;
  selected?: boolean;
  flash?: boolean;
  dim?: boolean;
  limits?: boolean;
  duplicate?: boolean;
  warning?: string | null;
  compact?: boolean;
  tooltip?: ReactNode;
  onClick?: () => void;
  draggable?: boolean;
  dragging?: boolean;
  onDragStart?: (event: DragEvent<HTMLButtonElement>) => void;
  onDragEnd?: (event: DragEvent<HTMLButtonElement>) => void;
  ariaLabel?: string;
}

/** One bin: an open-fronted box with a label strip, filled to its level */
export function BinTile(props: Readonly<TileProps>) {
  const { size, u, status, compact } = props;
  const width = Math.round(SIZE[size].w * u);
  const bodyHeight = Math.round(SIZE[size].h * u);
  const lines = u >= 80 ? 2 : 1;
  const labelFont = u >= 80 ? 11.5 : 10.5;
  const labelHeight = Math.round(lines * labelFont * 1.2 + 8);
  const scale = size === 'l' ? 1.25 : size === 'm' ? 1.1 : 1;
  const qtyFont = Math.max(13, Math.min(26, u * 0.24)) * scale;
  const subFont = Math.max(10, Math.min(12, u * 0.125));
  const color = STATUS_COLOR[status];
  const fill = status === 'unassigned' || props.fill === null || props.fill === undefined ? null : props.fill;
  const level = fill === null ? 0 : Math.max(0, Math.min(1, fill));
  const showThumb = !!props.thumbnail && !compact && size !== 's' && u >= 72;
  const thumb = Math.round(u * 0.26);

  const body: CSSProperties = { width, height: compact ? Math.round(bodyHeight * 0.9) : bodyHeight };

  if (compact) {
    body.borderBottom = '1px solid var(--mantine-color-default-border)';
    body.borderRadius = 3;
  }

  const tile = (
    <button
      type='button'
      className='vb-bin'
      data-status={status}
      data-selected={props.selected ? 'true' : undefined}
      data-flash={props.flash ? 'true' : undefined}
      data-dim={props.dim ? 'true' : undefined}
      data-dragging={props.dragging ? 'true' : undefined}
      data-static={props.onClick ? undefined : 'true'}
      draggable={props.draggable || undefined}
      onDragStart={props.onDragStart}
      onDragEnd={props.onDragEnd}
      onClick={props.onClick}
      tabIndex={props.onClick ? 0 : -1}
      aria-label={props.ariaLabel ?? props.title}
      style={{ width }}
    >
      <div className='vb-body' style={body}>
        {fill !== null && (
          <div
            className='vb-level'
            style={{
              height: `${level * 100}%`,
              background: `var(--mantine-color-${color}-filled)`
            }}
          />
        )}
        {!compact && (
          <div className='vb-content'>
            {props.primary !== undefined && (
              <span className='vb-qty' style={{ fontSize: qtyFont }}>
                {props.primary}
              </span>
            )}
            {props.secondary && (
              <span className='vb-sub' style={{ fontSize: subFont }}>
                {props.secondary}
              </span>
            )}
          </div>
        )}
        {showThumb && (
          <img
            className='vb-thumb'
            src={props.thumbnail ?? undefined}
            alt=''
            width={thumb}
            height={thumb}
            loading='lazy'
          />
        )}
        {!compact && (
          <div className='vb-mark'>
            {props.limits && (
              <IconFlag size={14} color='var(--mantine-color-orange-filled)' aria-label='Runs out first' />
            )}
            {props.duplicate && (
              <IconCopy size={14} color='var(--mantine-color-dimmed)' aria-label='Same stock as another bin' />
            )}
            {props.warning && (
              <IconHelpCircle size={14} color='var(--mantine-color-red-filled)' aria-label={props.warning} />
            )}
            {status === 'low' && (
              <IconAlertTriangle size={14} color='var(--mantine-color-yellow-filled)' aria-label='Below minimum' />
            )}
            {status === 'empty' && (
              <IconCircleX size={14} color='var(--mantine-color-red-filled)' aria-label='Empty' />
            )}
          </div>
        )}
      </div>
      {!compact && (
        <div className='vb-label' style={{ width, height: labelHeight, fontSize: labelFont }}>
          <span className='vb-clamp' style={{ WebkitLineClamp: lines }}>
            {props.title}
          </span>
        </div>
      )}
    </button>
  );

  if (!props.tooltip || compact) {
    return tile;
  }

  return (
    <Tooltip label={props.tooltip} openDelay={350} multiline maw={280} withArrow position='top'>
      {tile}
    </Tooltip>
  );
}

function tooltipFor(item: LayoutBin, data: BinData, limits: boolean): ReactNode {
  const units = data.part?.units ? ` ${data.part.units}` : '';
  const rows: string[] = [];

  if (data.part?.ipn) {
    rows.push(data.part.ipn);
  }

  if (data.bound) {
    rows.push(`${fmtQty(data.quantity)}${units} in the bin · ${STATUS_LABEL[data.status]}`);
  } else {
    rows.push('Not set to a part or location');
  }

  if (item.min !== null || item.max !== null) {
    const levels = [
      item.min !== null ? `minimum ${fmtQty(item.min)}` : '',
      item.max !== null ? `filled to ${fmtQty(item.max)}` : ''
    ].filter(Boolean);

    rows.push(levels.join(', '));
  }

  if (data.covers !== null) {
    rows.push(`Enough for ${fmtQty(data.covers)} units (${fmtQty(data.per_unit)} each)`);
  } else if (data.consumable) {
    rows.push('Consumable: not counted per unit');
  }

  if (limits) {
    rows.push('Runs out first');
  }

  if (data.held_back > 0) {
    rows.push(`${fmtQty(data.held_back)} not available (status)`);
  }

  if (data.location) {
    rows.push(data.location.pathstring);
  }

  return (
    <div style={{ fontSize: 12, lineHeight: 1.35 }}>
      <div style={{ fontWeight: 600 }}>{data.part?.name ?? data.title}</div>
      {rows.map((row) => (
        <div key={row}>{row}</div>
      ))}
    </div>
  );
}

export type ShowMode = 'quantity' | 'covers';

/** The frame around the rows: a bench top with legs, or the uprights of a shelving unit */
export function Frame({
  kind,
  u,
  compact,
  rows,
  flash,
  names = true
}: Readonly<{
  kind: UnitKind;
  u: number;
  compact?: boolean;
  rows: { key: string; name: string; content: ReactNode }[];
  flash?: boolean;
  /** Show the name of each row above it */
  names?: boolean;
}>) {
  const top = compact ? 3 : 6;
  const shelving = kind === 'shelving';

  return (
    <div
      className='vb-unit'
      data-flash={flash ? 'true' : undefined}
      style={{ display: 'inline-flex', alignItems: 'stretch', gap: 0, maxWidth: 'none' }}
    >
      {shelving && <div className='vb-upright' />}
      <div style={{ display: 'flex', flexDirection: 'column', gap: compact ? 6 : Math.round(u * 0.2) }}>
        {rows.map((row, index) => (
          <div key={row.key}>
            {names && !compact && (row.name || rows.length > 1) && (
              <div
                className='vb-rowname'
                style={{ fontSize: 11, margin: `0 ${shelving ? 8 : 2}px 5px` }}
              >
                {row.name || `Row ${index + 1}`}
              </div>
            )}
            <div style={{ padding: `0 ${shelving ? (compact ? 3 : 8) : compact ? 2 : 6}px` }}>
              {row.content}
            </div>
            <div className='vb-top' style={{ height: top }} />
            {!shelving && !compact && (
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0 14px' }}>
                <div className='vb-leg' />
                <div className='vb-leg' />
              </div>
            )}
          </div>
        ))}
      </div>
      {shelving && <div className='vb-upright' />}
    </div>
  );
}

/** Extra width the frame takes besides the bins, in pixels */
export function frameChrome(kind: UnitKind, compact = false): number {
  if (kind === 'shelving') {
    return compact ? 18 : 28;
  }

  return compact ? 4 : 12;
}

/** The drawing of a unit, with the stock in each bin */
export function Bench({
  layout,
  bins,
  u,
  mode = 'quantity',
  selected,
  flashing,
  flashUnit,
  limited,
  dimOthers,
  showImages = true,
  compact,
  onSelect
}: Readonly<{
  layout: Layout;
  bins: Record<string, BinData>;
  u: number;
  mode?: ShowMode;
  selected?: string | null;
  flashing?: Set<string>;
  flashUnit?: boolean;
  limited?: Set<string>;
  /** Fade every bin which is not in this set */
  dimOthers?: Set<string> | null;
  showImages?: boolean;
  compact?: boolean;
  onSelect?: (id: string) => void;
}>) {
  const gap = compact ? 3 : gapPx(u);

  const tile = (item: LayoutBin) => {
    const data = bins[item.id];

    if (!data) {
      return <BinTile key={item.id} title={item.label || 'New bin'} size={item.size} u={u} status='unassigned' compact={compact} />;
    }

    const limits = !!limited?.has(item.id);
    let primary: string | undefined;
    let secondary: string | undefined;

    if (!data.bound) {
      primary = undefined;
      secondary = 'Unassigned';
    } else if (!data.part) {
      primary = fmtShort(data.quantity);
      secondary = data.contents.length === 1 ? '1 part' : `${data.contents.length} parts`;
    } else if (mode === 'covers' && data.covers !== null) {
      primary = fmtShort(data.covers);
      secondary = 'units';
    } else {
      primary = fmtShort(data.quantity);
      secondary =
        mode === 'covers'
          ? data.consumable
            ? 'consumable'
            : 'not on BOM'
          : data.part.units || undefined;
    }

    const warning = data.part_missing
      ? 'The part no longer exists'
      : data.location_missing
        ? 'The location no longer exists'
        : null;

    return (
      <BinTile
        key={item.id}
        title={data.title}
        size={item.size}
        u={u}
        status={data.status}
        primary={primary}
        secondary={secondary}
        fill={data.fill}
        thumbnail={showImages ? data.part?.thumbnail : null}
        selected={selected === item.id}
        flash={flashing?.has(item.id)}
        dim={!!dimOthers && !dimOthers.has(item.id)}
        limits={limits}
        duplicate={data.duplicates.length > 0}
        warning={warning}
        compact={compact}
        tooltip={tooltipFor(item, data, limits)}
        onClick={onSelect ? () => onSelect(item.id) : undefined}
        ariaLabel={`${data.title}, ${data.bound ? fmtQty(data.quantity) : 'unassigned'}, ${STATUS_LABEL[data.status]}`}
      />
    );
  };

  return (
    <Frame
      kind={layout.kind}
      u={u}
      compact={compact}
      flash={flashUnit}
      rows={layout.rows.map((row) => ({
        key: row.id,
        name: row.name,
        content: (
          <div className='vb-row' style={{ gap, minHeight: compact ? 8 : Math.round(u * 0.5) }}>
            {row.columns.map((column) => (
              <div key={column.id} className='vb-col' style={{ gap: compact ? 2 : 4 }}>
                {column.bins.map(tile)}
              </div>
            ))}
            {row.columns.length === 0 && !compact && (
              <span style={{ color: 'var(--mantine-color-dimmed)', fontSize: 12, padding: '0 4px 6px' }}>
                No bins in this row
              </span>
            )}
          </div>
        )
      }))}
    />
  );
}
