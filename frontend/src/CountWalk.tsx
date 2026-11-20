import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Button,
  Checkbox,
  Group,
  Modal,
  NumberInput,
  Progress,
  ScrollArea,
  Stack,
  Table,
  Text,
  Title
} from '@mantine/core';
import { IconArrowLeft, IconCheck, IconPlayerSkipForward } from '@tabler/icons-react';
import { useEffect, useMemo, useRef, useState } from 'react';

import { Bench, frameChrome, widestRow } from './Bench';
import { apiData, apiError, apiUrl, countable, fmtQty, plural } from './format';
import type { AdjustResult, LayoutBin, UnitData } from './types';
import { useWidth } from './ui';

interface Entry {
  id: string;
  title: string;
  before: number;
  after: number;
}

/** Count a unit bin by bin, in the order the bins are laid out */
export function CountWalk({
  context,
  unit,
  opened,
  onClose,
  onUnit
}: Readonly<{
  context: InvenTreePluginContext;
  unit: UnitData;
  opened: boolean;
  onClose: () => void;
  onUnit: (unit: UnitData) => void;
}>) {
  const api = useRef(context.api);
  api.current = context.api;

  // The bins to count are fixed when the walk starts
  const [queue, setQueue] = useState<LayoutBin[]>([]);
  const [index, setIndex] = useState(0);
  const [entries, setEntries] = useState<Record<string, Entry>>({});
  const [skipped, setSkipped] = useState<Set<string>>(new Set());
  const [quantity, setQuantity] = useState<number | string>('');
  const [blind, setBlind] = useState(unit.settings.blind_count);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [finished, setFinished] = useState(false);
  const input = useRef<HTMLInputElement | null>(null);
  const [mapRef, mapWidth] = useWidth<HTMLDivElement>();

  useEffect(() => {
    if (!opened) {
      return;
    }

    setQueue(countable(unit.layout, unit.bins));
    setIndex(0);
    setEntries({});
    setSkipped(new Set());
    setQuantity('');
    setBlind(unit.settings.blind_count);
    setError(null);
    setFinished(false);
    // Only when the walk is opened: the unit changes with every count
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [opened]);

  const current = !finished && index < queue.length ? queue[index] : null;
  const data = current ? unit.bins[current.id] : null;

  useEffect(() => {
    if (opened && current) {
      const timer = window.setTimeout(() => input.current?.focus(), 60);
      return () => window.clearTimeout(timer);
    }
  }, [opened, current?.id]);

  // The small drawing which shows where the bin is
  const mapUnit = useMemo(() => {
    const chrome = frameChrome(unit.layout.kind, true);
    const columns = Math.max(1, ...unit.layout.rows.map((row) => row.columns.length));
    const space = Math.max(mapWidth, 200) - chrome - columns * 3 - 8;

    return Math.max(8, Math.min(34, space / widestRow(unit.layout)));
  }, [unit.layout, mapWidth]);

  const go = (next: number) => {
    setError(null);
    setQuantity('');

    if (next >= queue.length) {
      setFinished(true);
    } else {
      setIndex(Math.max(0, next));
    }
  };

  const save = (value: number) => {
    if (!current || !data || busy) {
      return;
    }

    setBusy(true);
    setError(null);

    const before = data.quantity;

    api.current
      .post(apiUrl(`unit/${unit.location.pk}/bin/${current.id}/adjust/`), {
        action: 'count',
        quantity: value
      })
      .then((response) => {
        const result = apiData<AdjustResult>(response, 'done');

        setEntries((previous) => ({
          ...previous,
          [current.id]: { id: current.id, title: data.title, before, after: value }
        }));
        setSkipped((previous) => {
          const next = new Set(previous);
          next.delete(current.id);
          return next;
        });
        onUnit(result.unit);
        go(index + 1);
      })
      .catch((err) => setError(apiError(err, 'Could not save the count')))
      .finally(() => setBusy(false));
  };

  const skip = () => {
    if (!current) {
      return;
    }

    if (!entries[current.id]) {
      setSkipped((previous) => new Set(previous).add(current.id));
    }

    go(index + 1);
  };

  const value = typeof quantity === 'number' ? quantity : Number.NaN;
  const valid = !Number.isNaN(value) && value >= 0;
  const counted = Object.values(entries);
  const changed = counted.filter((entry) => entry.before !== entry.after);
  const units = data?.part?.units ? ` ${data.part.units}` : '';

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size='lg'
      zIndex={300}
      closeOnClickOutside={false}
      title={
        <Text fw={700} fz='lg'>
          Count {unit.location.name}
        </Text>
      }
    >
      {queue.length === 0 ? (
        <Stack>
          <Text size='sm'>
            There is nothing to count here: no bin of this unit is set to a part.
          </Text>
          <Group justify='flex-end'>
            <Button variant='default' onClick={onClose}>
              Close
            </Button>
          </Group>
        </Stack>
      ) : finished ? (
        <Stack gap='md'>
          <Alert color='teal' icon={<IconCheck size={18} />} title='Count finished'>
            {plural(counted.length, 'bin')} counted, {changed.length} changed
            {skipped.size > 0 ? `, ${skipped.size} skipped` : ''}.
          </Alert>
          {changed.length > 0 && (
            <ScrollArea.Autosize mah={320}>
              <Table verticalSpacing={4} horizontalSpacing='xs'>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Bin</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Was</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Counted</Table.Th>
                    <Table.Th style={{ textAlign: 'right' }}>Difference</Table.Th>
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {changed.map((entry) => (
                    <Table.Tr key={entry.id}>
                      <Table.Td>{entry.title}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>{fmtQty(entry.before)}</Table.Td>
                      <Table.Td style={{ textAlign: 'right' }}>{fmtQty(entry.after)}</Table.Td>
                      <Table.Td
                        style={{
                          textAlign: 'right',
                          color:
                            entry.after < entry.before
                              ? 'var(--mantine-color-red-text)'
                              : 'var(--mantine-color-teal-text)'
                        }}
                      >
                        {entry.after > entry.before ? '+' : ''}
                        {fmtQty(Math.round((entry.after - entry.before) * 1000) / 1000)}
                      </Table.Td>
                    </Table.Tr>
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea.Autosize>
          )}
          {skipped.size > 0 && (
            <Text size='sm' c='dimmed'>
              Skipped:{' '}
              {queue
                .filter((item) => skipped.has(item.id))
                .map((item) => unit.bins[item.id]?.title ?? 'bin')
                .join(', ')}
            </Text>
          )}
          <Group justify='flex-end'>
            {skipped.size > 0 && (
              <Button
                variant='default'
                onClick={() => {
                  const first = queue.findIndex((item) => skipped.has(item.id));
                  setFinished(false);
                  setIndex(Math.max(0, first));
                }}
              >
                Count the skipped bins
              </Button>
            )}
            <Button onClick={onClose}>Done</Button>
          </Group>
        </Stack>
      ) : (
        current &&
        data && (
          <Stack gap='md'>
            <div>
              <Group justify='space-between' mb={4}>
                <Text size='sm' c='dimmed'>
                  Bin {index + 1} of {queue.length}
                </Text>
                <Text size='sm' c='dimmed'>
                  {counted.length} counted
                </Text>
              </Group>
              <Progress value={(index / queue.length) * 100} size='sm' />
            </div>

            <div ref={mapRef} style={{ overflow: 'hidden', textAlign: 'center' }} aria-hidden>
              <Bench
                layout={unit.layout}
                bins={unit.bins}
                u={mapUnit}
                compact
                selected={current.id}
                dimOthers={new Set([current.id])}
              />
            </div>

            <div style={{ textAlign: 'center' }}>
              <Title order={3}>{data.title}</Title>
              <Text size='sm' c='dimmed'>
                {[data.part?.ipn, data.position].filter(Boolean).join(' · ')}
              </Text>
              {!blind && (
                <Text size='sm' mt={6}>
                  InvenTree has{' '}
                  <b>
                    {fmtQty(data.quantity)}
                    {units}
                  </b>
                  {entries[current.id] ? ' (already counted)' : ''}
                </Text>
              )}
            </div>

            <NumberInput
              ref={input}
              className='vb-num'
              aria-label='Quantity counted'
              placeholder='Count'
              value={quantity}
              onChange={setQuantity}
              min={0}
              decimalScale={data.part?.trackable ? 0 : 3}
              allowNegative={false}
              hideControls
              inputMode='decimal'
              suffix={units || undefined}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && valid) {
                  save(value);
                }
              }}
            />

            {error && (
              <Alert color='red' p='xs'>
                {error}
              </Alert>
            )}

            <Group justify='space-between' wrap='nowrap'>
              <Group gap='xs' wrap='nowrap'>
                <Button
                  variant='default'
                  leftSection={<IconArrowLeft size={16} />}
                  disabled={index === 0 || busy}
                  onClick={() => go(index - 1)}
                >
                  Back
                </Button>
                <Button
                  variant='default'
                  leftSection={<IconPlayerSkipForward size={16} />}
                  disabled={busy}
                  onClick={skip}
                >
                  Skip
                </Button>
              </Group>
              <Group gap='xs' wrap='nowrap'>
                {!blind && (
                  <Button
                    variant='light'
                    disabled={busy}
                    onClick={() => save(data.quantity)}
                    title='The bin holds what InvenTree says'
                  >
                    As expected
                  </Button>
                )}
                <Button disabled={!valid} loading={busy} onClick={() => save(value)}>
                  Save and next
                </Button>
              </Group>
            </Group>

            <Group justify='space-between'>
              <Checkbox
                size='xs'
                label='Hide what InvenTree expects'
                checked={blind}
                onChange={(event) => {
                  setBlind(event.currentTarget.checked);
                  // Back to the number, so that the count can be typed straight away
                  input.current?.focus();
                }}
              />
              <Button variant='subtle' size='compact-sm' onClick={() => setFinished(true)}>
                Finish now
              </Button>
            </Group>
          </Stack>
        )
      )}
    </Modal>
  );
}
