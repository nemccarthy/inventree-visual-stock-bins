import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Alert, Center, Group, Loader, ScrollArea, Stack, Table, Text } from '@mantine/core';
import { IconLayoutGrid } from '@tabler/icons-react';
import { useEffect, useRef, useState } from 'react';

import { apiData, apiError, apiUrl, fmtQty, unitUrl } from './format';
import type { AttentionResult } from './types';
import { AppLink, StatusBadge } from './ui';

/** Dashboard item: the bins which are empty or below their minimum */
export function VirtualBinsDashboardItem({
  context
}: Readonly<{ context: InvenTreePluginContext }>) {
  const api = useRef(context.api);
  api.current = context.api;

  const [data, setData] = useState<AttentionResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    api.current
      .get(apiUrl('attention/'))
      .then((response) => {
        if (!cancelled) {
          setData(apiData<AttentionResult>(response, 'bins'));
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(apiError(err, 'Could not load the bins'));
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (error) {
    return (
      <Alert color='red' p='xs'>
        {error}
      </Alert>
    );
  }

  if (!data) {
    return (
      <Center h={120}>
        <Loader size='sm' />
      </Center>
    );
  }

  const total = data.empty + data.low;

  return (
    <Stack gap='xs' h='100%'>
      <Group justify='space-between' wrap='nowrap'>
        <Group gap={6} wrap='nowrap'>
          <IconLayoutGrid size={18} />
          <Text fw={600}>Bins to refill</Text>
        </Group>
        <AppLink context={context} to={unitUrl()}>
          All units
        </AppLink>
      </Group>
      <Text size='sm' c={data.empty > 0 ? 'red' : 'dimmed'}>
        {data.units === 0
          ? 'No bins have been set up yet.'
          : total === 0
            ? 'Every bin is at or above its minimum.'
            : `${data.empty} empty, ${data.low} below minimum.`}
      </Text>
      {data.bins.length > 0 && (
        <ScrollArea style={{ flex: 1 }} type='auto'>
          <Table verticalSpacing={3} horizontalSpacing='xs'>
            <Table.Tbody>
              {data.bins.map((item) => (
                <Table.Tr key={`${item.unit}:${item.id}`}>
                  <Table.Td>
                    <AppLink context={context} to={unitUrl(item.unit)}>
                      {item.title}
                    </AppLink>
                    <Text size='xs' c='dimmed'>
                      {item.unit_name} · {fmtQty(item.quantity)}
                      {item.min !== null ? ` of at least ${fmtQty(item.min)}` : ''}
                      {item.elsewhere <= 0 ? ' · none elsewhere' : ''}
                    </Text>
                  </Table.Td>
                  <Table.Td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                    <StatusBadge status={item.status} />
                  </Table.Td>
                </Table.Tr>
              ))}
            </Table.Tbody>
          </Table>
        </ScrollArea>
      )}
    </Stack>
  );
}
