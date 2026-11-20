import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Modal,
  NumberInput,
  ScrollArea,
  Select,
  Stack,
  Table,
  Text
} from '@mantine/core';
import { IconCheck, IconCopy, IconRefresh } from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { doneText } from './BinDrawer';
import { apiData, apiError, apiUrl, fmtQty, plural } from './format';
import type { AdjustResult, RefillLine, RefillResult, UnitData } from './types';
import { StatusBadge } from './ui';

function Line({
  line,
  canAdjust,
  busy,
  onTopUp
}: Readonly<{
  line: RefillLine;
  canAdjust: boolean;
  busy: boolean;
  onTopUp: (line: RefillLine, quantity: number, source: number | null) => void;
}>) {
  const [quantity, setQuantity] = useState<number | string>(Math.min(line.refill, line.elsewhere) || line.refill);
  const [source, setSource] = useState('auto');

  const chosen = source === 'auto' ? null : line.sources.find((entry) => String(entry.pk) === source);
  const onHand = chosen ? chosen.quantity : line.elsewhere;
  const value = typeof quantity === 'number' ? quantity : Number.NaN;
  const valid = !Number.isNaN(value) && value > 0 && value <= onHand + 1e-9;
  const units = line.part?.units ? ` ${line.part.units}` : '';

  return (
    <Table.Tr>
      <Table.Td>
        <Text size='sm' fw={600}>
          {line.title}
        </Text>
        <Text size='xs' c='dimmed'>
          {[line.part?.ipn, line.position].filter(Boolean).join(' · ')}
        </Text>
      </Table.Td>
      <Table.Td>
        <StatusBadge status={line.status} />
      </Table.Td>
      <Table.Td style={{ textAlign: 'right', whiteSpace: 'nowrap', fontVariantNumeric: 'tabular-nums' }}>
        {fmtQty(line.quantity)}
        {units}
        <Text size='xs' c='dimmed'>
          {line.min !== null ? `min ${fmtQty(line.min)}` : ''}
          {line.min !== null && line.max !== null ? ', ' : ''}
          {line.max !== null ? `fill to ${fmtQty(line.max)}` : ''}
        </Text>
      </Table.Td>
      <Table.Td style={{ minWidth: 220 }}>
        {line.elsewhere <= 0 ? (
          <Badge color='red' variant='light' radius='sm'>
            None elsewhere
          </Badge>
        ) : line.serialized ? (
          <Text size='xs' c='dimmed'>
            Serial-numbered stock: move it in InvenTree
          </Text>
        ) : (
          <Select
            size='xs'
            aria-label='Take the stock from'
            data={[
              { value: 'auto', label: `Oldest first (${fmtQty(line.elsewhere)} elsewhere)` },
              ...line.sources.map((entry) => ({
                value: String(entry.pk),
                label: `${entry.location_name}: ${fmtQty(entry.quantity)}${entry.batch ? ` (batch ${entry.batch})` : ''}`
              }))
            ]}
            value={source}
            onChange={(next) => setSource(next ?? 'auto')}
            allowDeselect={false}
            comboboxProps={{ withinPortal: true, zIndex: 400 }}
          />
        )}
      </Table.Td>
      <Table.Td style={{ width: 110 }}>
        <NumberInput
          size='xs'
          aria-label='Quantity to top up'
          value={quantity}
          onChange={setQuantity}
          min={0}
          allowNegative={false}
          hideControls
          decimalScale={line.part?.trackable ? 0 : 3}
          disabled={line.elsewhere <= 0 || line.serialized || !canAdjust}
          error={line.elsewhere > 0 && !Number.isNaN(value) && value > onHand + 1e-9 ? `Only ${fmtQty(onHand)}` : undefined}
          styles={{ input: { textAlign: 'right' } }}
        />
      </Table.Td>
      <Table.Td style={{ textAlign: 'right' }}>
        <Button
          size='xs'
          disabled={!valid || line.elsewhere <= 0 || line.serialized || !canAdjust}
          loading={busy}
          onClick={() => onTopUp(line, value, chosen ? chosen.pk : null)}
        >
          Top up
        </Button>
      </Table.Td>
    </Table.Tr>
  );
}

/** The bins which are due a refill, where the stock is, and a button to move it */
export function RefillList({
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

  const pk = unit.location.pk;
  const [data, setData] = useState<RefillResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(() => {
    setLoading(true);

    return api.current
      .get(apiUrl(`unit/${pk}/refill/`))
      .then((response) => {
        setData(apiData<RefillResult>(response, 'lines'));
        setError(null);
      })
      .catch((err) => setError(apiError(err, 'Could not load the refill list')))
      .finally(() => setLoading(false));
  }, [pk]);

  useEffect(() => {
    if (opened) {
      setData(null);
      setMessage(null);
      setCopied(false);
      load();
    }
  }, [opened, load]);

  const topUp = (line: RefillLine, quantity: number, source: number | null) => {
    setBusy(line.bin);
    setError(null);
    setMessage(null);

    api.current
      .post(apiUrl(`unit/${pk}/bin/${line.bin}/adjust/`), {
        action: 'refill',
        quantity,
        source: source ?? undefined
      })
      .then((response) => {
        const result = apiData<AdjustResult>(response, 'done');

        setMessage(`${line.title}: ${doneText(result.done, line.part?.units ?? '')}`);
        onUnit(result.unit);

        return load();
      })
      .catch((err) => setError(apiError(err, 'Could not top up the bin')))
      .finally(() => setBusy(null));
  };

  const copy = () => {
    if (!data) {
      return;
    }

    const text = [
      `Refill list: ${unit.location.name}`,
      ...data.lines.map((line) => {
        const from = line.sources[0]?.location_name ?? 'none in stock elsewhere';

        return `${line.title}${line.part?.ipn ? ` (${line.part.ipn})` : ''}\t${fmtQty(line.refill)}\t${from}\t${line.position}`;
      })
    ].join('\n');

    navigator.clipboard
      ?.writeText(text)
      .then(() => setCopied(true))
      .catch(() => setCopied(false));
  };

  const lines = data?.lines ?? [];
  const short = lines.filter((line) => line.elsewhere <= 0).length;

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      size='min(1000px, 96vw)'
      zIndex={300}
      title={
        <Text fw={700} fz='lg'>
          Refill {unit.location.name}
        </Text>
      }
    >
      <Stack gap='md'>
        {error && (
          <Alert color='red' p='xs'>
            {error}
          </Alert>
        )}
        {message && (
          <Alert color='teal' p='xs' icon={<IconCheck size={16} />}>
            {message}
          </Alert>
        )}

        {!data ? (
          <Center h={160}>{loading ? <Loader /> : null}</Center>
        ) : lines.length === 0 ? (
          <Alert color='teal' icon={<IconCheck size={18} />}>
            Nothing to refill: every bin with a minimum is at or above it.
          </Alert>
        ) : (
          <>
            <Group justify='space-between'>
              <Text size='sm' c='dimmed'>
                {plural(lines.length, 'bin')} empty or below minimum
                {short > 0 ? `, ${short} with no stock elsewhere` : ''}. Topping up moves the stock
                in InvenTree.
              </Text>
              <Group gap='xs'>
                <Button
                  variant='default'
                  size='xs'
                  leftSection={copied ? <IconCheck size={14} /> : <IconCopy size={14} />}
                  onClick={copy}
                >
                  {copied ? 'Copied' : 'Copy list'}
                </Button>
                <Button
                  variant='default'
                  size='xs'
                  leftSection={<IconRefresh size={14} />}
                  loading={loading}
                  onClick={load}
                >
                  Refresh
                </Button>
              </Group>
            </Group>
            <ScrollArea type='auto'>
              <Table verticalSpacing={6} horizontalSpacing='xs' style={{ minWidth: 760 }}>
                <Table.Thead>
                  <Table.Tr>
                    <Table.Th>Bin</Table.Th>
                    <Table.Th />
                    <Table.Th style={{ textAlign: 'right' }}>In the bin</Table.Th>
                    <Table.Th>From</Table.Th>
                    <Table.Th>Top up by</Table.Th>
                    <Table.Th />
                  </Table.Tr>
                </Table.Thead>
                <Table.Tbody>
                  {lines.map((line) => (
                    <Line
                      // A new row after a top-up, so that the suggested quantity is fresh
                      key={`${line.bin}:${line.quantity}:${line.elsewhere}`}
                      line={line}
                      canAdjust={data.permissions.adjust}
                      busy={busy === line.bin}
                      onTopUp={topUp}
                    />
                  ))}
                </Table.Tbody>
              </Table>
            </ScrollArea>
          </>
        )}
      </Stack>
    </Modal>
  );
}
