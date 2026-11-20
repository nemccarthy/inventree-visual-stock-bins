import type { InvenTreePluginContext } from '@inventreedb/ui';
import { Alert } from '@mantine/core';

import { UnitView } from './UnitView';

/** The Bins panel on a stock location page */
export function VirtualBinsLocationPanel({
  context
}: Readonly<{ context: InvenTreePluginContext }>) {
  const raw = context.context?.location_id ?? context.id ?? null;
  const locationId = raw === null ? Number.NaN : Number(raw);

  if (!Number.isInteger(locationId) || locationId <= 0) {
    return <Alert color='red'>No stock location is associated with this page.</Alert>;
  }

  return <UnitView key={locationId} context={context} locationId={locationId} variant='panel' />;
}
