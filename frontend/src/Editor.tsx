import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Alert,
  Button,
  Divider,
  Group,
  Modal,
  NumberInput,
  Paper,
  SegmentedControl,
  Stack,
  Text,
  TextInput,
  Textarea,
  Tooltip
} from '@mantine/core';
import {
  IconArrowDown,
  IconArrowLeft,
  IconArrowRight,
  IconArrowUp,
  IconCopy,
  IconPlus,
  IconStack2,
  IconTrash
} from '@tabler/icons-react';
import { type DragEvent, useEffect, useMemo, useRef, useState } from 'react';

import { BinTile, Frame, U_MAX, frameChrome, gapPx, rowUnits } from './Bench';
import {
  SIZE,
  SIZE_LABEL,
  apiData,
  apiError,
  apiUrl,
  cloneLayout,
  fmtQty,
  fmtShort,
  newBin,
  plural
} from './format';
import {
  type Nudge,
  type Target,
  addRow,
  canNudge,
  countBins,
  duplicateBin,
  duplicateIds,
  insertBin,
  locate,
  moveBin,
  moveRow,
  nudgeBin,
  removeBin,
  removeRow,
  updateBin,
  updateRow
} from './layoutOps';
import type {
  AutofillResult,
  BinData,
  BinSize,
  Layout,
  LayoutBin,
  UnitData,
  UnitKind,
  UnitLocation
} from './types';
import { RemoteSelect, locationChoice, partChoice, useWidth } from './ui';

interface Names {
  parts: Record<number, { name: string; ipn: string }>;
  locations: Record<number, { name: string; pathstring: string }>;
}

function seedNames(location: UnitLocation, bins: Record<string, BinData> | undefined, product: UnitData['product'] | undefined): Names {
  const names: Names = {
    parts: {},
    locations: { [location.pk]: { name: location.name, pathstring: location.pathstring } }
  };

  if (product) {
    names.parts[product.pk] = { name: product.name, ipn: product.ipn };
  }

  for (const data of Object.values(bins ?? {})) {
    if (data.part) {
      names.parts[data.part.pk] = { name: data.part.name, ipn: data.part.ipn };
    }

    if (data.location) {
      names.locations[data.location.pk] = {
        name: data.location.name,
        pathstring: data.location.pathstring
      };
    }
  }

  return names;
}

function titleOf(item: LayoutBin, names: Names): string {
  if (item.label) {
    return item.label;
  }

  if (item.part !== null) {
    return names.parts[item.part]?.name ?? `Part ${item.part}`;
  }

  if (item.location !== null) {
    return names.locations[item.location]?.name ?? `Location ${item.location}`;
  }

  return 'Unassigned';
}

function partLabel(pk: number | null, names: Names): string | null {
  if (pk === null) {
    return null;
  }

  const part = names.parts[pk];

  return part ? (part.ipn ? `${part.name} (${part.ipn})` : part.name) : null;
}

/** The form for the selected bin */
function BinForm({
  context,
  location,
  layout,
  item,
  names,
  duplicate,
  onChange,
  onNames,
  onNudge,
  onDuplicate,
  onRemove
}: Readonly<{
  context: InvenTreePluginContext;
  location: UnitLocation;
  layout: Layout;
  item: LayoutBin;
  names: Names;
  duplicate: boolean;
  onChange: (patch: Partial<LayoutBin>) => void;
  onNames: (update: (names: Names) => Names) => void;
  onNudge: (direction: Nudge) => void;
  onDuplicate: () => void;
  onRemove: () => void;
}>) {
  const can = canNudge(layout, item.id);
  const badLevels = item.min !== null && item.max !== null && item.max < item.min;

  const nudge = (direction: Nudge, label: string, icon: React.ReactNode) => (
    <Tooltip label={label} openDelay={300}>
      <ActionIcon
        variant='default'
        size='lg'
        aria-label={label}
        disabled={!can[direction]}
        onClick={() => onNudge(direction)}
      >
        {icon}
      </ActionIcon>
    </Tooltip>
  );

  return (
    <Stack gap='sm'>
      <Text fw={700}>Bin</Text>
      <RemoteSelect
        context={context}
        url='/api/part/'
        params={{ virtual: false }}
        toChoice={partChoice}
        value={item.part}
        current={partLabel(item.part, names)}
        onChange={(next, row) => {
          if (row) {
            onNames((previous) => ({
              ...previous,
              parts: { ...previous.parts, [row.pk]: { name: row.name, ipn: row.IPN ?? '' } }
            }));
          }

          onChange({ part: next });
        }}
        label='Part'
        placeholder='Search for a part'
      />
      <RemoteSelect
        context={context}
        url='/api/stock/location/'
        toChoice={locationChoice}
        value={item.location}
        current={item.location !== null ? (names.locations[item.location]?.pathstring ?? null) : null}
        onChange={(next, row) => {
          if (row) {
            onNames((previous) => ({
              ...previous,
              locations: {
                ...previous.locations,
                [row.pk]: { name: row.name, pathstring: row.pathstring }
              }
            }));
          }

          onChange({ location: next });
        }}
        label='Location of its own'
        description={`Leave empty to show the stock of the part anywhere in ${location.name}. Set it when this bin is a stock location itself.`}
        placeholder={`In ${location.name}`}
      />
      {duplicate && (
        <Alert color='yellow' p='xs'>
          Another bin is set to the same part and location, so both will show the same stock.
        </Alert>
      )}
      <TextInput
        label='Label'
        placeholder={item.part !== null || item.location !== null ? titleOf({ ...item, label: '' }, names) : 'What the bin is for'}
        value={item.label}
        maxLength={60}
        onChange={(event) => onChange({ label: event.currentTarget.value })}
      />
      <div>
        <Text size='sm' fw={500} mb={4}>
          Size
        </Text>
        <SegmentedControl
          fullWidth
          size='xs'
          data={(Object.keys(SIZE) as BinSize[]).map((size) => ({
            value: size,
            label: SIZE_LABEL[size]
          }))}
          value={item.size}
          onChange={(next) => onChange({ size: next as BinSize })}
        />
      </div>
      <Group grow align='flex-start'>
        <NumberInput
          label='Minimum'
          description='Refill below this'
          value={item.min ?? ''}
          min={0}
          allowNegative={false}
          hideControls
          onChange={(next) => onChange({ min: typeof next === 'number' ? next : null })}
        />
        <NumberInput
          label='Fill to'
          description='What the bin holds'
          value={item.max ?? ''}
          min={0}
          allowNegative={false}
          hideControls
          error={badLevels ? 'Below the minimum' : undefined}
          onChange={(next) => onChange({ max: typeof next === 'number' ? next : null })}
        />
      </Group>
      <Textarea
        label='Note'
        placeholder='Shown when the bin is opened'
        autosize
        minRows={1}
        maxRows={4}
        maxLength={200}
        value={item.note}
        onChange={(event) => onChange({ note: event.currentTarget.value })}
      />
      <div>
        <Text size='sm' fw={500} mb={4}>
          Position
        </Text>
        <Group gap={6}>
          {nudge('left', 'Move left', <IconArrowLeft size={18} />)}
          {nudge('right', 'Move right', <IconArrowRight size={18} />)}
          {nudge('up', 'Move up in the stack', <IconArrowUp size={18} />)}
          {nudge('down', 'Move down in the stack', <IconArrowDown size={18} />)}
          {nudge('stack-left', 'Stack on the column to the left', <IconStack2 size={18} style={{ transform: 'scaleX(-1)' }} />)}
          {nudge('stack-right', 'Stack on the column to the right', <IconStack2 size={18} />)}
        </Group>
        <Text size='xs' c='dimmed' mt={4}>
          Or drag the bin: onto a gap for a column of its own, onto another bin to stack it.
        </Text>
      </div>
      <Group gap='xs'>
        <Button variant='default' size='xs' leftSection={<IconCopy size={14} />} onClick={onDuplicate}>
          Duplicate
        </Button>
        <Button
          variant='light'
          color='red'
          size='xs'
          leftSection={<IconTrash size={14} />}
          onClick={onRemove}
        >
          Remove bin
        </Button>
      </Group>
    </Stack>
  );
}

/** The schematic editor: drag bins into rows, columns and stacks, and set what each one holds */
export function Editor({
  context,
  location,
  initial,
  bins,
  product,
  configured,
  onSaved,
  onCancel,
  onDeleted
}: Readonly<{
  context: InvenTreePluginContext;
  location: UnitLocation;
  initial: Layout;
  bins?: Record<string, BinData>;
  product?: UnitData['product'];
  configured: boolean;
  onSaved: (unit: UnitData) => void;
  onCancel: () => void;
  onDeleted: () => void;
}>) {
  const api = useRef(context.api);
  api.current = context.api;

  const [layout, setLayout] = useState<Layout>(() => cloneLayout(initial));
  const [names, setNames] = useState<Names>(() => seedNames(location, bins, product));
  const [selected, setSelected] = useState<string | null>(null);
  const [dragging, setDragging] = useState<string | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [confirm, setConfirm] = useState<'cancel' | 'delete' | null>(null);
  const [bomPart, setBomPart] = useState<number | null>(null);
  const [bomLevels, setBomLevels] = useState('direct');
  const [canvasRef, canvasWidth] = useWidth<HTMLDivElement>();

  const start = useMemo(() => JSON.stringify(initial), [initial]);
  const dirty = JSON.stringify(layout) !== start;
  const duplicates = useMemo(() => duplicateIds(layout), [layout]);
  const total = countBins(layout);
  const found = selected ? locate(layout, selected) : null;

  useEffect(() => {
    if (selected && !found) {
      setSelected(null);
    }
  }, [selected, found]);

  // Warn before the page is left with unsaved changes
  useEffect(() => {
    if (!dirty) {
      return;
    }

    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };

    window.addEventListener('beforeunload', warn);

    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const chrome = frameChrome(layout.kind);
  // Room for the "add" button at the end of every row, and for wider drop gaps
  const widest = Math.max(1, ...layout.rows.map((row) => rowUnits(row.columns) + 0.9 + row.columns.length * 0.06));
  const u = Math.max(64, Math.min(U_MAX - 12, Math.floor((Math.max(canvasWidth, 320) - chrome - 8) / widest)));
  const gap = gapPx(u) + 6;

  const change = (next: Layout) => {
    setLayout(next);
    setMessage(null);
    setError(null);
  };

  const drop = (target: Target) => (event: DragEvent<HTMLElement>) => {
    event.preventDefault();
    event.stopPropagation();

    const id = dragging ?? event.dataTransfer.getData('text/plain');

    setOver(null);
    setDragging(null);

    if (id) {
      change(moveBin(layout, id, target));
      setSelected(id);
    }
  };

  const hover = (key: string) => ({
    onDragOver: (event: DragEvent<HTMLElement>) => {
      if (!dragging) {
        return;
      }

      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';

      if (over !== key) {
        setOver(key);
      }
    },
    onDragLeave: () => {
      setOver((current) => (current === key ? null : current));
    }
  });

  const addBin = (rowId: string) => {
    const item = newBin();

    change(insertBin(layout, item, { type: 'column', row: rowId, before: null }));
    setSelected(item.id);
  };

  const autofill = (source: 'stock' | 'children' | 'bom') => {
    setBusy(source);
    setError(null);
    setMessage(null);

    api.current
      .post(apiUrl(`unit/${location.pk}/autofill/`), {
        source,
        assembly: source === 'bom' ? bomPart : undefined,
        levels: bomLevels,
        layout
      })
      .then((response) => {
        const result = apiData<AutofillResult>(response, 'layout');

        setNames((previous) => {
          const parts = { ...previous.parts };

          const locations = { ...previous.locations };

          for (const part of Object.values(result.parts)) {
            parts[part.pk] = { name: part.name, ipn: part.ipn };
          }

          for (const place of Object.values(result.locations ?? {})) {
            locations[place.pk] = { name: place.name, pathstring: place.pathstring };
          }

          return { parts, locations };
        });
        setLayout(result.layout);

        if (result.found === 0) {
          setMessage(
            source === 'stock'
              ? `There is no stock in ${location.name} to make bins from.`
              : source === 'children'
                ? `${location.name} has no locations below it.`
                : 'That BOM is empty.'
          );
        } else if (result.added === 0) {
          setMessage('Every one of those already has a bin.');
        } else {
          setMessage(
            `${plural(result.added, 'bin')} added below${result.found > result.added ? ` (${result.found - result.added} already had one)` : ''}. Drag them into place.`
          );
        }
      })
      .catch((err) => setError(apiError(err, 'Could not make the bins')))
      .finally(() => setBusy(null));
  };

  const save = () => {
    setBusy('save');
    setError(null);

    api.current
      .put(apiUrl(`unit/${location.pk}/layout/`), { layout })
      .then((response) => onSaved(apiData<UnitData>(response, 'layout')))
      .catch((err) => setError(apiError(err, 'Could not save the layout')))
      .finally(() => setBusy(null));
  };

  const remove = () => {
    setBusy('delete');

    api.current
      .delete(apiUrl(`unit/${location.pk}/layout/`))
      .then(() => onDeleted())
      .catch((err) => {
        setError(apiError(err, 'Could not remove the bins'));
        setConfirm(null);
      })
      .finally(() => setBusy(null));
  };

  const tile = (item: LayoutBin) => {
    const live = bins?.[item.id];
    const bound = item.part !== null || item.location !== null;
    const levels =
      item.min !== null || item.max !== null
        ? `${item.min !== null ? fmtQty(item.min) : '–'} / ${item.max !== null ? fmtQty(item.max) : '–'}`
        : undefined;

    return (
      <BinTile
        title={titleOf(item, names)}
        size={item.size}
        u={u}
        status={bound ? 'ok' : 'unassigned'}
        primary={live && bound ? fmtShort(live.quantity) : undefined}
        secondary={levels ?? (bound ? undefined : 'Unassigned')}
        fill={null}
        selected={selected === item.id}
        duplicate={duplicates.has(item.id)}
        draggable
        dragging={dragging === item.id}
        onDragStart={(event) => {
          event.dataTransfer.setData('text/plain', item.id);
          event.dataTransfer.effectAllowed = 'move';
          setDragging(item.id);
        }}
        onDragEnd={() => {
          setDragging(null);
          setOver(null);
        }}
        onClick={() => setSelected(item.id)}
        ariaLabel={`${titleOf(item, names)}. Select to edit`}
      />
    );
  };

  const rows = layout.rows.map((row, rowIndex) => ({
    key: row.id,
    name: '',
    content: (
      <div>
        <Group gap={6} mb={6} wrap='nowrap'>
          <TextInput
            size='xs'
            aria-label={`Name of row ${rowIndex + 1}`}
            placeholder={layout.kind === 'shelving' ? `Shelf ${rowIndex + 1}` : `Row ${rowIndex + 1} (e.g. Left bay)`}
            value={row.name}
            maxLength={60}
            onChange={(event) => change(updateRow(layout, row.id, { name: event.currentTarget.value }))}
            style={{ width: 220 }}
          />
          <Tooltip label='Move the row up' openDelay={300}>
            <ActionIcon
              variant='subtle'
              color='gray'
              aria-label='Move the row up'
              disabled={rowIndex === 0}
              onClick={() => change(moveRow(layout, row.id, -1))}
            >
              <IconArrowUp size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label='Move the row down' openDelay={300}>
            <ActionIcon
              variant='subtle'
              color='gray'
              aria-label='Move the row down'
              disabled={rowIndex === layout.rows.length - 1}
              onClick={() => change(moveRow(layout, row.id, 1))}
            >
              <IconArrowDown size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip
            label={row.columns.length > 0 ? 'Remove the row and its bins' : 'Remove the row'}
            openDelay={300}
          >
            <ActionIcon
              variant='subtle'
              color='red'
              aria-label='Remove the row'
              disabled={layout.rows.length === 1 && row.columns.length === 0}
              onClick={() => change(removeRow(layout, row.id))}
            >
              <IconTrash size={16} />
            </ActionIcon>
          </Tooltip>
        </Group>
        <div className='vb-row' style={{ minHeight: Math.round(u * 0.9) }}>
          {row.columns.map((column) => {
            const gapKey = `gap:${row.id}:${column.id}`;

            return (
              <div key={column.id} style={{ display: 'flex', alignItems: 'flex-end', alignSelf: 'stretch' }}>
                <div
                  className='vb-gap'
                  style={{ width: gap }}
                  data-active={dragging ? 'true' : undefined}
                  data-over={over === gapKey ? 'true' : undefined}
                  {...hover(gapKey)}
                  onDrop={drop({ type: 'column', row: row.id, before: column.id })}
                />
                <div className='vb-col' style={{ gap: 0 }}>
                  {column.bins.map((item) => {
                    const slotKey = `slot:${column.id}:${item.id}`;

                    return (
                      <div
                        key={item.id}
                        style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}
                        {...hover(slotKey)}
                        onDrop={drop({ type: 'stack', column: column.id, before: item.id })}
                      >
                        <div
                          className='vb-slot'
                          data-active={dragging && dragging !== item.id ? 'true' : undefined}
                          data-over={over === slotKey && dragging !== item.id ? 'true' : undefined}
                        />
                        {tile(item)}
                      </div>
                    );
                  })}
                  <div
                    className='vb-slot'
                    data-active={dragging ? 'true' : undefined}
                    data-over={over === `end:${column.id}` ? 'true' : undefined}
                    {...hover(`end:${column.id}`)}
                    onDrop={drop({ type: 'stack', column: column.id, before: null })}
                  />
                </div>
              </div>
            );
          })}
          <div
            className='vb-gap'
            style={{ width: gap, minHeight: Math.round(u * 0.9) }}
            data-active={dragging ? 'true' : undefined}
            data-over={over === `gap:${row.id}:end` ? 'true' : undefined}
            {...hover(`gap:${row.id}:end`)}
            onDrop={drop({ type: 'column', row: row.id, before: null })}
          />
          <button
            type='button'
            className='vb-add'
            style={{ width: Math.round(u * 0.8), height: Math.round(u * 0.8), fontSize: 11, marginBottom: 6 }}
            onClick={() => addBin(row.id)}
            {...hover(`gap:${row.id}:end`)}
            onDrop={drop({ type: 'column', row: row.id, before: null })}
          >
            <IconPlus size={18} />
            Add bin
          </button>
        </div>
      </div>
    )
  }));

  return (
    <Stack gap='md'>
      <Group justify='space-between' align='flex-start'>
        <div>
          <Text fw={700} fz='lg'>
            {configured ? 'Edit the bins of' : 'Set up the bins of'} {location.name}
          </Text>
          <Text size='sm' c='dimmed'>
            Lay the bins out as they look from the front. {plural(total, 'bin')}
            {dirty ? ', not saved yet' : ''}.
          </Text>
        </div>
        <Group gap='xs'>
          <Button
            variant='default'
            disabled={busy !== null}
            onClick={() => (dirty ? setConfirm('cancel') : onCancel())}
          >
            Cancel
          </Button>
          <Button onClick={save} loading={busy === 'save'} disabled={busy !== null && busy !== 'save'}>
            Save layout
          </Button>
        </Group>
      </Group>

      {error && (
        <Alert color='red' p='xs'>
          {error}
        </Alert>
      )}
      {message && (
        <Alert color='blue' p='xs'>
          {message}
        </Alert>
      )}

      <div style={{ display: 'flex', gap: 16, alignItems: 'flex-start', flexWrap: 'wrap' }}>
        <div ref={canvasRef} style={{ flex: '1 1 520px', minWidth: 0, overflowX: 'auto', paddingBottom: 8 }}>
          <Frame kind={layout.kind} u={u} rows={rows} names={false} />
          <div style={{ marginTop: 14 }}>
            <Button
              variant='default'
              size='xs'
              leftSection={<IconPlus size={14} />}
              disabled={layout.rows.length >= 12}
              onClick={() => change(addRow(layout))}
            >
              {layout.kind === 'shelving' ? 'Add a shelf' : 'Add a row'}
            </Button>
          </div>
        </div>

        <Paper withBorder p='md' style={{ flex: '0 1 330px', minWidth: 280 }}>
          {found ? (
            <BinForm
              context={context}
              location={location}
              layout={layout}
              item={found.bin}
              names={names}
              duplicate={duplicates.has(found.bin.id)}
              onChange={(patch) => change(updateBin(layout, found.bin.id, patch))}
              onNames={setNames}
              onNudge={(direction) => change(nudgeBin(layout, found.bin.id, direction))}
              onDuplicate={() => {
                const result = duplicateBin(layout, found.bin.id);
                change(result.layout);
                setSelected(result.id);
              }}
              onRemove={() => change(removeBin(layout, found.bin.id))}
            />
          ) : (
            <Stack gap='sm'>
              <Text fw={700}>Unit</Text>
              <div>
                <Text size='sm' fw={500} mb={4}>
                  Drawn as
                </Text>
                <SegmentedControl
                  fullWidth
                  size='xs'
                  data={[
                    { value: 'bench', label: 'Bench' },
                    { value: 'shelving', label: 'Shelving' }
                  ]}
                  value={layout.kind}
                  onChange={(next) => change({ ...layout, kind: next as UnitKind })}
                />
              </div>
              <RemoteSelect
                context={context}
                url='/api/part/'
                params={{ assembly: true }}
                toChoice={partChoice}
                value={layout.product}
                current={partLabel(layout.product, names)}
                onChange={(next, row) => {
                  if (row) {
                    setNames((previous) => ({
                      ...previous,
                      parts: { ...previous.parts, [row.pk]: { name: row.name, ipn: row.IPN ?? '' } }
                    }));
                  }

                  change({ ...layout, product: next });
                }}
                label='Product built here'
                description='Optional. Each bin then shows how many units it is enough for.'
                placeholder='Search for an assembly'
              />

              <Divider label='Add bins' labelPosition='left' />
              <Button
                variant='default'
                size='xs'
                loading={busy === 'stock'}
                disabled={busy !== null && busy !== 'stock'}
                onClick={() => autofill('stock')}
              >
                One for each part stocked here
              </Button>
              <Button
                variant='default'
                size='xs'
                loading={busy === 'children'}
                disabled={busy !== null && busy !== 'children'}
                onClick={() => autofill('children')}
              >
                One for each location below this one
              </Button>
              <RemoteSelect
                context={context}
                url='/api/part/'
                params={{ assembly: true }}
                toChoice={partChoice}
                value={bomPart}
                current={partLabel(bomPart, names)}
                onChange={(next, row) => {
                  if (row) {
                    setNames((previous) => ({
                      ...previous,
                      parts: { ...previous.parts, [row.pk]: { name: row.name, ipn: row.IPN ?? '' } }
                    }));
                  }

                  setBomPart(next);
                }}
                label='From a BOM'
                placeholder='Search for an assembly'
                size='xs'
              />
              <Group gap='xs' wrap='nowrap'>
                <SegmentedControl
                  size='xs'
                  data={[
                    { value: 'direct', label: 'Its own lines' },
                    { value: 'all', label: 'Every level' }
                  ]}
                  value={bomLevels}
                  onChange={setBomLevels}
                  style={{ flex: 1 }}
                />
                <Button
                  size='xs'
                  variant='default'
                  loading={busy === 'bom'}
                  disabled={bomPart === null || (busy !== null && busy !== 'bom')}
                  onClick={() => autofill('bom')}
                >
                  Add
                </Button>
              </Group>
              <Text size='xs' c='dimmed'>
                Or use "Add bin" at the end of a row. Select a bin to set its part, size and levels.
              </Text>

              {configured && (
                <>
                  <Divider />
                  <Button
                    variant='subtle'
                    color='red'
                    size='xs'
                    leftSection={<IconTrash size={14} />}
                    onClick={() => setConfirm('delete')}
                  >
                    Remove the bins from this location
                  </Button>
                </>
              )}
            </Stack>
          )}
          {found && (
            <Button variant='subtle' size='compact-xs' mt='sm' onClick={() => setSelected(null)}>
              Back to the unit settings
            </Button>
          )}
        </Paper>
      </div>

      <Modal
        opened={confirm !== null}
        onClose={() => setConfirm(null)}
        zIndex={320}
        centered
        title={
          <Text fw={700}>
            {confirm === 'delete' ? 'Remove the bins?' : 'Discard the changes?'}
          </Text>
        }
      >
        <Stack>
          <Text size='sm'>
            {confirm === 'delete'
              ? `The layout of ${location.name} is removed. The location and its stock are not touched.`
              : 'The changes to the layout have not been saved.'}
          </Text>
          <Group justify='flex-end'>
            <Button variant='default' onClick={() => setConfirm(null)}>
              Keep editing
            </Button>
            {confirm === 'delete' ? (
              <Button color='red' loading={busy === 'delete'} onClick={remove}>
                Remove the bins
              </Button>
            ) : (
              <Button
                color='red'
                onClick={() => {
                  setConfirm(null);
                  onCancel();
                }}
              >
                Discard
              </Button>
            )}
          </Group>
        </Stack>
      </Modal>
    </Stack>
  );
}
