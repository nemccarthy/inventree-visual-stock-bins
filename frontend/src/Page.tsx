import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  Alert,
  Anchor,
  Badge,
  Button,
  Center,
  Group,
  Loader,
  Paper,
  SimpleGrid,
  Stack,
  Text,
  Title
} from '@mantine/core';
import {
  IconArrowLeft,
  IconBuildingWarehouse,
  IconLayoutGrid,
  IconRefresh,
  IconTable
} from '@tabler/icons-react';
import { useCallback, useEffect, useRef, useState } from 'react';

import { UnitView } from './UnitView';
import { apiData, apiError, apiUrl, fmtQty, plural, summaryText, unitUrl } from './format';
import type { UnitSummary, UnitsResult } from './types';
import { RemoteSelect, locationChoice, useStyles } from './ui';

function readUrl(): { unit: number | null; kiosk: boolean } {
  const params = new URLSearchParams(window.location.search);
  const unit = Number(params.get('unit'));

  return {
    unit: Number.isInteger(unit) && unit > 0 ? unit : null,
    kiosk: ['1', 'true'].includes(params.get('kiosk') ?? '')
  };
}

function UnitCard({ unit, onOpen }: Readonly<{ unit: UnitSummary; onOpen: () => void }>) {
  const summary = unit.summary;
  const names = unit.attention.slice(0, 3).map((item) => item.title);
  const more = unit.attention.length - names.length;

  return (
    <button type='button' className='vb-card' onClick={onOpen}>
      <Group justify='space-between' wrap='nowrap' align='flex-start'>
        <div style={{ minWidth: 0 }}>
          <Group gap={8} wrap='nowrap'>
            {unit.kind === 'shelving' ? <IconTable size={18} /> : <IconBuildingWarehouse size={18} />}
            <Text fw={700} fz='lg' truncate>
              {unit.location.name}
            </Text>
          </Group>
          <Text size='xs' c='dimmed' truncate>
            {unit.location.pathstring}
          </Text>
        </div>
        <Text size='sm' c='dimmed' style={{ whiteSpace: 'nowrap' }}>
          {plural(summary.bins, 'bin')}
        </Text>
      </Group>
      <Group gap={6} mt='sm'>
        {summary.empty > 0 && (
          <Badge color='red' variant='light' radius='sm'>
            {summary.empty} empty
          </Badge>
        )}
        {summary.low > 0 && (
          <Badge color='yellow' variant='light' radius='sm'>
            {summary.low} below minimum
          </Badge>
        )}
        {summary.empty === 0 && summary.low === 0 && (
          <Badge color='teal' variant='light' radius='sm'>
            {summaryText(summary)}
          </Badge>
        )}
      </Group>
      {names.length > 0 && (
        <Text size='xs' c='dimmed' mt={6} lineClamp={2}>
          {names.join(', ')}
          {more > 0 ? ` and ${more} more` : ''}
        </Text>
      )}
      {unit.product && unit.buildable && (
        <Text size='sm' mt={8}>
          Enough for <b>{fmtQty(unit.buildable.units)}</b> × {unit.product.name}
        </Text>
      )}
    </button>
  );
}

/** The Bins page: every unit, and the drawing of the one which is opened */
export function VirtualBinsPage({ context }: Readonly<{ context: InvenTreePluginContext }>) {
  useStyles();

  const api = useRef(context.api);
  api.current = context.api;

  const [route, setRoute] = useState(readUrl);
  const [data, setData] = useState<UnitsResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pick, setPick] = useState<number | null>(null);
  const [pickName, setPickName] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);

    api.current
      .get(apiUrl('units/'))
      .then((response) => {
        setData(apiData<UnitsResult>(response, 'units'));
        setError(null);
      })
      .catch((err) => setError(apiError(err, 'Could not load the units')))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (route.unit === null) {
      load();
    }
  }, [route.unit, load]);

  // Back and forward in the browser
  useEffect(() => {
    const sync = () => setRoute(readUrl());

    window.addEventListener('popstate', sync);

    return () => window.removeEventListener('popstate', sync);
  }, []);

  const open = (pk: number | null) => {
    context.navigate(unitUrl(pk));
    setRoute({ unit: pk, kiosk: false });
  };

  if (route.unit !== null) {
    return (
      <Stack gap='md' p='md'>
        <div>
          <Anchor component='button' type='button' size='sm' onClick={() => open(null)}>
            <Group gap={4} wrap='nowrap'>
              <IconArrowLeft size={14} />
              All units
            </Group>
          </Anchor>
        </div>
        <UnitView
          // A different unit starts from scratch
          key={route.unit}
          context={context}
          locationId={route.unit}
          variant='page'
          startFull={route.kiosk}
        />
      </Stack>
    );
  }

  return (
    <Stack gap='md' p='md'>
      <Group justify='space-between' align='flex-end'>
        <div>
          <Group gap='sm'>
            <IconLayoutGrid size={26} />
            <Title order={2}>Bins</Title>
          </Group>
          <Text size='sm' c='dimmed'>
            Benches and shelving units, drawn bin by bin with what is in each.
          </Text>
        </div>
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

      {error && (
        <Alert color='red' title='Could not load the units'>
          {error}
        </Alert>
      )}

      {!data && !error && (
        <Center h={200}>
          <Loader />
        </Center>
      )}

      {data && data.units.length === 0 && (
        <Paper withBorder p='xl'>
          <Stack align='center' gap='xs'>
            <IconLayoutGrid size={36} color='var(--mantine-color-dimmed)' />
            <Text fw={700}>No units yet</Text>
            <Text size='sm' c='dimmed' ta='center' maw={520}>
              A unit is a stock location - a workbench, a shelving unit - whose bins have been
              drawn. Choose a location below to draw its bins, or use the Bins panel on the page of
              any stock location.
            </Text>
          </Stack>
        </Paper>
      )}

      {data && data.units.length > 0 && (
        <SimpleGrid cols={{ base: 1, sm: 2, lg: 3 }} spacing='md'>
          {data.units.map((unit) => (
            <UnitCard key={unit.location.pk} unit={unit} onOpen={() => open(unit.location.pk)} />
          ))}
        </SimpleGrid>
      )}

      {data?.permissions.layout && (
        <Paper withBorder p='md'>
          <Group align='flex-end' gap='sm'>
            <div style={{ flex: '1 1 320px', maxWidth: 480 }}>
              <RemoteSelect
                context={context}
                url='/api/stock/location/'
                toChoice={locationChoice}
                value={pick}
                current={pickName}
                onChange={(next, row) => {
                  setPick(next);
                  setPickName(row?.pathstring ?? null);
                }}
                label='Draw the bins of another location'
                placeholder='Search for a stock location'
              />
            </div>
            <Button disabled={pick === null} onClick={() => open(pick)}>
              Open
            </Button>
          </Group>
        </Paper>
      )}
    </Stack>
  );
}
