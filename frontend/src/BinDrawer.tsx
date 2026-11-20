import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Divider,
  Drawer,
  Group,
  NumberInput,
  SegmentedControl,
  Select,
  Stack,
  Table,
  Text,
  TextInput
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconCheck,
  IconExternalLink,
  IconFlag
} from '@tabler/icons-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  STATUS_LABEL,
  apiData,
  apiError,
  apiUrl,
  fmtAgo,
  fmtQty,
  locationUrl,
  partUrl,
  stockItemUrl
} from './format';
import type {
  AdjustAction,
  AdjustDone,
  AdjustResult,
  BinData,
  LayoutBin,
  RefillSource,
  UnitData
} from './types';
import { AppLink, RemoteSelect, StatusBadge, locationChoice } from './ui';

const ACTIONS: { value: AdjustAction; label: string }[] = [
  { value: 'count', label: 'Count' },
  { value: 'add', label: 'Add' },
  { value: 'remove', label: 'Remove' },
  { value: 'move', label: 'Move out' },
  { value: 'refill', label: 'Top up' }
];

const HELP: Record<AdjustAction, string> = {
  count: 'Enter what is in the bin now. InvenTree is set to that quantity.',
  add: 'Stock which is new to InvenTree, put straight into this bin.',
  remove: 'Stock which is gone: used, scrapped or lost. Oldest stock is taken first.',
  move: 'Take stock out of this bin and put it in another location.',
  refill: 'Move stock which InvenTree already holds elsewhere into this bin.'
};

const SUBMIT: Record<AdjustAction, string> = {
  count: 'Save count',
  add: 'Add stock',
  remove: 'Remove stock',
  move: 'Move stock',
  refill: 'Top up'
};

export function doneText(done: AdjustDone, units: string): string {
  const unit = units ? ` ${units}` : '';
  const change = `${fmtQty(done.before ?? 0)} → ${fmtQty(done.after ?? 0)}${unit}`;

  switch (done.action) {
    case 'count':
      return done.before === done.after
        ? `Counted: ${fmtQty(done.after ?? 0)}${unit}, as expected.`
        : `Counted: ${change}.`;
    case 'add':
      return `Added: ${change}.`;
    case 'remove':
      return `Removed: ${change}.`;
    case 'move':
      return `Moved to ${done.destination}: ${change}.`;
    case 'refill':
      return `Topped up${done.sources?.length ? ` from ${done.sources.join(', ')}` : ''}: ${change}.`;
    default:
      return 'Done.';
  }
}

function Fact({ label, children }: Readonly<{ label: string; children: React.ReactNode }>) {
  return (
    <div>
      <Text size='xs' c='dimmed'>
        {label}
      </Text>
      <Text size='sm' fw={600} component='div'>
        {children}
      </Text>
    </div>
  );
}

/** The form which changes the stock of one bin */
export function AdjustForm({
  context,
  unit,
  item,
  data,
  initial = 'count',
  onUnit
}: Readonly<{
  context: InvenTreePluginContext;
  unit: UnitData;
  item: LayoutBin;
  data: BinData;
  initial?: AdjustAction;
  onUnit: (unit: UnitData) => void;
}>) {
  const api = useRef(context.api);
  api.current = context.api;

  const [action, setAction] = useState<AdjustAction>(initial);
  const [quantity, setQuantity] = useState<number | string>('');
  const [notes, setNotes] = useState('');
  const [destination, setDestination] = useState<number | null>(null);
  const [destinationName, setDestinationName] = useState<string | null>(null);
  const [source, setSource] = useState<string>('auto');
  const [sources, setSources] = useState<RefillSource[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<AdjustDone | null>(null);

  const units = data.part?.units ?? '';
  const pk = unit.location.pk;

  // A different bin: start again
  useEffect(() => {
    setAction(initial);
    setQuantity('');
    setNotes('');
    setDestination(null);
    setDestinationName(null);
    setSource('auto');
    setSources(null);
    setError(null);
    setDone(null);
  }, [item.id, initial]);

  // Where a top-up can come from
  useEffect(() => {
    if (action !== 'refill') {
      return;
    }

    let cancelled = false;

    api.current
      .get(apiUrl(`unit/${pk}/bin/${item.id}/sources/`))
      .then((response) => {
        if (!cancelled) {
          setSources(apiData<{ sources: RefillSource[] }>(response, 'sources').sources);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setSources([]);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [action, pk, item.id, data.quantity]);

  const pick = (next: AdjustAction) => {
    setAction(next);
    setError(null);
    setDone(null);
    setQuantity(next === 'refill' && data.refill > 0 ? data.refill : '');
  };

  const value = typeof quantity === 'number' ? quantity : Number.NaN;
  const valid =
    !Number.isNaN(value) &&
    (action === 'count' ? value >= 0 : value > 0) &&
    (action !== 'move' || destination !== null);

  const chosen = source === 'auto' ? null : sources?.find((entry) => String(entry.pk) === source);
  const onHand = chosen ? chosen.quantity : data.elsewhere;

  const submit = () => {
    if (!valid || busy) {
      return;
    }

    setBusy(true);
    setError(null);
    setDone(null);

    api.current
      .post(apiUrl(`unit/${pk}/bin/${item.id}/adjust/`), {
        action,
        quantity: value,
        notes: notes.trim() || undefined,
        destination: action === 'move' ? destination : undefined,
        source: action === 'refill' && chosen ? chosen.pk : undefined
      })
      .then((response) => {
        const result = apiData<AdjustResult>(response, 'done');

        setDone(result.done);
        setQuantity('');
        setNotes('');
        onUnit(result.unit);
      })
      .catch((err) => setError(apiError(err, 'Could not change the stock')))
      .finally(() => setBusy(false));
  };

  const available = ACTIONS.filter(
    (entry) => entry.value !== 'refill' || data.elsewhere > 0 || action === 'refill'
  );

  return (
    <Stack gap='sm'>
      <SegmentedControl
        fullWidth
        size='sm'
        data={available}
        value={action}
        onChange={(next) => pick(next as AdjustAction)}
      />
      <Text size='xs' c='dimmed'>
        {HELP[action]}
      </Text>
      <NumberInput
        className='vb-num'
        aria-label={action === 'count' ? 'Quantity counted' : 'Quantity'}
        placeholder={action === 'count' ? 'Counted' : 'Quantity'}
        value={quantity}
        onChange={setQuantity}
        min={0}
        decimalScale={data.part?.trackable ? 0 : 3}
        allowNegative={false}
        hideControls
        inputMode='decimal'
        suffix={units ? ` ${units}` : undefined}
        onKeyDown={(event) => {
          if (event.key === 'Enter') {
            submit();
          }
        }}
        data-autofocus
      />
      {action === 'move' && (
        <RemoteSelect
          context={context}
          url='/api/stock/location/'
          params={{ structural: false }}
          toChoice={locationChoice}
          value={destination}
          current={destinationName}
          onChange={(next, row) => {
            setDestination(next);
            setDestinationName(row?.pathstring ?? null);
          }}
          label='To'
          placeholder='Search for a location'
        />
      )}
      {action === 'refill' && (
        <>
          <Select
            label='From'
            data={[
              { value: 'auto', label: `Oldest stock first (${fmtQty(data.elsewhere)} elsewhere)` },
              ...(sources ?? []).map((entry) => ({
                value: String(entry.pk),
                label: `${entry.location_name}: ${fmtQty(entry.quantity)}${entry.batch ? ` (batch ${entry.batch})` : ''}`
              }))
            ]}
            value={source}
            onChange={(next) => setSource(next ?? 'auto')}
            allowDeselect={false}
            comboboxProps={{ withinPortal: true, zIndex: 400 }}
          />
          {!Number.isNaN(value) && value > onHand && (
            <Text size='xs' c='red'>
              Only {fmtQty(onHand)} is available {chosen ? 'in that stock item' : 'elsewhere'}.
            </Text>
          )}
        </>
      )}
      <TextInput
        label='Note'
        placeholder='Optional, kept in the stock history'
        value={notes}
        onChange={(event) => setNotes(event.currentTarget.value)}
        maxLength={200}
      />
      {error && (
        <Alert color='red' p='xs'>
          {error}
        </Alert>
      )}
      {done && (
        <Alert color='teal' p='xs' icon={<IconCheck size={16} />}>
          {doneText(done, units)}
        </Alert>
      )}
      <Button onClick={submit} loading={busy} disabled={!valid}>
        {SUBMIT[action]}
      </Button>
    </Stack>
  );
}

/** Everything about one bin, and the form to change its stock */
export function BinDrawer({
  context,
  unit,
  binId,
  onClose,
  onUnit
}: Readonly<{
  context: InvenTreePluginContext;
  unit: UnitData;
  binId: string | null;
  onClose: () => void;
  onUnit: (unit: UnitData) => void;
}>) {
  const item = useMemo(() => {
    if (!binId) {
      return null;
    }

    for (const row of unit.layout.rows) {
      for (const column of row.columns) {
        const found = column.bins.find((candidate) => candidate.id === binId);

        if (found) {
          return found;
        }
      }
    }

    return null;
  }, [unit.layout, binId]);

  const data: BinData | null = item ? (unit.bins[item.id] ?? null) : null;
  const units = data?.part?.units ? ` ${data.part.units}` : '';
  const limits = !!data && !!unit.buildable?.limited_by.includes(data.id);
  const canAdjust = !!data?.part && !data.serialized && unit.permissions.adjust;

  return (
    <Drawer
      opened={!!item && !!data}
      onClose={onClose}
      position='right'
      size='min(460px, 96vw)'
      zIndex={300}
      title={
        data ? (
          <Group gap='sm' wrap='nowrap'>
            <Text fw={700} fz='lg' lineClamp={2}>
              {data.title}
            </Text>
            <StatusBadge status={data.status} />
          </Group>
        ) : (
          'Bin'
        )
      }
    >
      {item && data && (
        <Stack gap='md'>
          <Text size='sm' c='dimmed'>
            {unit.location.name}
            {data.position ? ` · ${data.position}` : ''}
          </Text>

          {data.part && (
            <Group gap='sm' wrap='nowrap' align='flex-start'>
              {data.part.thumbnail && (
                <img
                  src={data.part.thumbnail}
                  alt=''
                  width={56}
                  height={56}
                  style={{ borderRadius: 6, objectFit: 'cover', flex: 'none' }}
                />
              )}
              <div style={{ minWidth: 0 }}>
                <AppLink context={context} to={partUrl(data.part.pk)}>
                  <Group gap={4} wrap='nowrap'>
                    {data.part.name}
                    <IconExternalLink size={13} />
                  </Group>
                </AppLink>
                <Text size='xs' c='dimmed' lineClamp={2}>
                  {[data.part.ipn, data.part.description !== data.part.name ? data.part.description : '']
                    .filter(Boolean)
                    .join(' · ')}
                </Text>
              </div>
            </Group>
          )}

          {data.location && (
            <Text size='sm'>
              Location:{' '}
              <AppLink context={context} to={locationUrl(data.location.pk)}>
                {data.location.pathstring}
              </AppLink>
            </Text>
          )}

          {data.part_missing && (
            <Alert color='red' p='xs' icon={<IconAlertTriangle size={16} />}>
              The part this bin was set to no longer exists. Edit the layout to choose another.
            </Alert>
          )}
          {data.location_missing && (
            <Alert color='red' p='xs' icon={<IconAlertTriangle size={16} />}>
              The location this bin was set to no longer exists. Edit the layout to choose another.
            </Alert>
          )}
          {!data.bound && (
            <Alert color='gray' p='xs'>
              This bin is a placeholder: it is not set to a part or a location. Edit the layout to
              set it.
            </Alert>
          )}
          {data.duplicates.length > 0 && (
            <Alert color='yellow' p='xs'>
              Shows the same stock as{' '}
              {data.duplicates.map((id) => unit.bins[id]?.position || 'another bin').join(' and ')}.
              Give each bin a location of its own to keep them apart.
            </Alert>
          )}

          {data.bound && (
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fill, minmax(120px, 1fr))',
                gap: '10px 16px'
              }}
            >
              <Fact label='In the bin'>
                {fmtQty(data.quantity)}
                {units}
              </Fact>
              {item.min !== null && <Fact label='Minimum'>{fmtQty(item.min)}</Fact>}
              {item.max !== null && <Fact label='Filled to'>{fmtQty(item.max)}</Fact>}
              {data.covers !== null && (
                <Fact label={`Enough for (${fmtQty(data.per_unit)} each)`}>
                  <Group gap={4} wrap='nowrap'>
                    {fmtQty(data.covers)} units
                    {limits && <IconFlag size={14} color='var(--mantine-color-orange-filled)' />}
                  </Group>
                </Fact>
              )}
              {data.part && <Fact label='Elsewhere in stock'>{fmtQty(data.elsewhere)}</Fact>}
            </div>
          )}

          {limits && (
            <Text size='sm' c='orange'>
              This bin runs out first: it limits how many {unit.product?.name ?? 'units'} can be
              built from this {unit.layout.kind === 'bench' ? 'bench' : 'unit'}.
            </Text>
          )}
          {data.consumable && (
            <Text size='sm' c='dimmed'>
              A consumable on the BOM of {unit.product?.name}: not counted per unit.
            </Text>
          )}
          {data.held_back > 0 && (
            <Text size='sm' c='dimmed'>
              {fmtQty(data.held_back)}
              {units} of this is not available for use (see the status below).
            </Text>
          )}
          {item.note && (
            <Text size='sm' style={{ whiteSpace: 'pre-wrap' }}>
              Note: {item.note}
            </Text>
          )}
          {data.part && (
            <Text size='xs' c='dimmed'>
              {data.counted
                ? `Last counted ${fmtAgo(data.counted.at)}${data.counted.by ? ` by ${data.counted.by}` : ''}: ${fmtQty(data.counted.quantity)}`
                : 'Not counted here yet'}
            </Text>
          )}

          {data.contents.length > 0 && (
            <Table verticalSpacing={4} horizontalSpacing='xs'>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>In this location</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>Quantity</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.contents.map((entry) => (
                  <Table.Tr key={entry.part}>
                    <Table.Td>
                      <AppLink context={context} to={partUrl(entry.part)}>
                        {entry.name}
                      </AppLink>
                      {entry.ipn && (
                        <Text size='xs' c='dimmed'>
                          {entry.ipn}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td style={{ textAlign: 'right' }}>{fmtQty(entry.quantity)}</Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}

          {data.part && data.items.length > 0 && (
            <Table verticalSpacing={4} horizontalSpacing='xs'>
              <Table.Thead>
                <Table.Tr>
                  <Table.Th>Stock item</Table.Th>
                  <Table.Th style={{ textAlign: 'right' }}>Quantity</Table.Th>
                  <Table.Th>Status</Table.Th>
                </Table.Tr>
              </Table.Thead>
              <Table.Tbody>
                {data.items.map((entry) => (
                  <Table.Tr key={entry.pk}>
                    <Table.Td>
                      <AppLink context={context} to={stockItemUrl(entry.pk)}>
                        {entry.serial ? `Serial ${entry.serial}` : `Item ${entry.pk}`}
                      </AppLink>
                      {(entry.batch || entry.location !== data.scope?.pk) && (
                        <Text size='xs' c='dimmed'>
                          {[
                            entry.batch ? `Batch ${entry.batch}` : '',
                            entry.location !== data.scope?.pk ? entry.location_name : ''
                          ]
                            .filter(Boolean)
                            .join(' · ')}
                        </Text>
                      )}
                    </Table.Td>
                    <Table.Td style={{ textAlign: 'right', fontVariantNumeric: 'tabular-nums' }}>
                      {fmtQty(entry.quantity)}
                    </Table.Td>
                    <Table.Td>
                      <Badge
                        size='sm'
                        variant='light'
                        radius='sm'
                        color={entry.available ? 'teal' : 'orange'}
                      >
                        {entry.status_label}
                      </Badge>
                    </Table.Td>
                  </Table.Tr>
                ))}
              </Table.Tbody>
            </Table>
          )}
          {data.item_count > data.items.length && (
            <Text size='xs' c='dimmed'>
              {fmtQty(data.item_count - data.items.length)} more stock items are not listed.
            </Text>
          )}

          {data.part && (
            <>
              <Divider />
              {canAdjust ? (
                <AdjustForm
                  context={context}
                  unit={unit}
                  item={item}
                  data={data}
                  onUnit={onUnit}
                />
              ) : data.serialized ? (
                <Text size='sm' c='dimmed'>
                  This bin holds serial-numbered stock. Open the stock items above to change them.
                </Text>
              ) : (
                <Text size='sm' c='dimmed'>
                  You do not have permission to change stock.
                </Text>
              )}
            </>
          )}

          {data.bound && !data.part && data.location && (
            <Text size='sm' c='dimmed'>
              This bin shows everything in its location ({STATUS_LABEL[data.status].toLowerCase()}).
              Set it to a part in the layout to count and top it up from here.
            </Text>
          )}
        </Stack>
      )}
    </Drawer>
  );
}
