import type { InvenTreePluginContext } from '@inventreedb/ui';

import { VirtualBinsDashboardItem } from './Dashboard';
import { VirtualBinsLocationPanel } from './LocationPanel';
import { VirtualBinsPage } from './Page';

/** The Bins page, at /web/plugin/virtual-bins/units */
export function renderVirtualBinsPage(context: InvenTreePluginContext) {
  return <VirtualBinsPage context={context} />;
}

/** The Bins panel on a stock location page */
export function renderVirtualBinsLocationPanel(context: InvenTreePluginContext) {
  return <VirtualBinsLocationPanel context={context} />;
}

/** The dashboard item */
export function renderVirtualBinsDashboardItem(context: InvenTreePluginContext) {
  return <VirtualBinsDashboardItem context={context} />;
}
