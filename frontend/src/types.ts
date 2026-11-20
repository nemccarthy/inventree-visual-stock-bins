export type BinSize = 's' | 'm' | 'l';
export type UnitKind = 'bench' | 'shelving';
export type BinStatus = 'ok' | 'low' | 'empty' | 'unassigned';

/** A bin as it is stored in the layout */
export interface LayoutBin {
  id: string;
  part: number | null;
  location: number | null;
  label: string;
  size: BinSize;
  min: number | null;
  max: number | null;
  note: string;
}

export interface LayoutColumn {
  id: string;
  bins: LayoutBin[];
}

export interface LayoutRow {
  id: string;
  name: string;
  columns: LayoutColumn[];
}

export interface Layout {
  version: number;
  kind: UnitKind;
  product: number | null;
  rows: LayoutRow[];
}

export interface PartInfo {
  pk: number;
  name: string;
  ipn: string;
  description: string;
  units: string;
  thumbnail: string | null;
  trackable: boolean;
  active: boolean;
  virtual: boolean;
  assembly: boolean;
}

export interface LocationInfo {
  pk: number;
  name: string;
  pathstring: string;
  structural: boolean;
}

export interface UnitLocation extends LocationInfo {
  description: string;
  external: boolean;
  parent: number | null;
}

export interface StockItemInfo {
  pk: number;
  part: number;
  quantity: number;
  batch: string;
  serial: string;
  status: number;
  status_label: string;
  available: boolean;
  location: number | null;
  location_name: string;
  updated: string | null;
}

export interface Counted {
  at: string;
  by: string;
  quantity: number;
}

/** A bin with its stock, as the server returns it */
export interface BinData {
  id: string;
  title: string;
  bound: boolean;
  part: PartInfo | null;
  part_missing: boolean;
  location: LocationInfo | null;
  location_missing: boolean;
  scope: LocationInfo | null;
  quantity: number;
  available: number;
  held_back: number;
  items: StockItemInfo[];
  item_count: number;
  serialized: boolean;
  contents: { part: number; name: string; ipn: string; quantity: number }[];
  status: BinStatus;
  fill: number | null;
  refill: number;
  per_unit: number | null;
  covers: number | null;
  consumable: boolean;
  elsewhere: number;
  counted: Counted | null;
  duplicates: string[];
  position: string;
}

export interface Summary {
  bins: number;
  ok: number;
  low: number;
  empty: number;
  unassigned: number;
}

export interface Buildable {
  units: number;
  limited_by: string[];
}

export interface Permissions {
  view: boolean;
  layout: boolean;
  adjust: boolean;
  add: boolean;
}

export interface InterfaceSettings {
  refresh_seconds: number;
  locate_seconds: number;
  show_images: boolean;
  blind_count: boolean;
}

export interface UnitData {
  configured: true;
  location: UnitLocation;
  layout: Layout;
  bins: Record<string, BinData>;
  summary: Summary;
  product: PartInfo | null;
  buildable: Buildable | null;
  generated: string;
  settings: InterfaceSettings;
  permissions: Permissions;
}

export interface UnconfiguredUnit {
  configured: false;
  location: UnitLocation;
  setup: { parts: number; children: number };
  settings: InterfaceSettings;
  permissions: Permissions;
}

export type UnitResult = UnitData | UnconfiguredUnit;

export interface AttentionBin {
  id: string;
  title: string;
  status: BinStatus;
  quantity: number;
  min: number | null;
  units: string;
  refill: number;
  elsewhere: number;
  position: string;
}

export interface UnitSummary {
  location: UnitLocation;
  kind: UnitKind;
  summary: Summary;
  product: PartInfo | null;
  buildable: Buildable | null;
  attention: AttentionBin[];
}

export interface UnitsResult {
  units: UnitSummary[];
  settings: InterfaceSettings;
  permissions: Permissions;
}

export interface RefillSource {
  pk: number;
  quantity: number;
  batch: string;
  location: number;
  location_name: string;
}

export interface RefillLine {
  bin: string;
  title: string;
  position: string;
  part: PartInfo | null;
  status: BinStatus;
  quantity: number;
  min: number | null;
  max: number | null;
  refill: number;
  elsewhere: number;
  serialized: boolean;
  sources: RefillSource[];
}

export interface RefillResult {
  location: UnitLocation;
  lines: RefillLine[];
  generated: string;
  permissions: Permissions;
}

export interface AttentionResult {
  units: number;
  empty: number;
  low: number;
  bins: (AttentionBin & { unit: number; unit_name: string })[];
}

export interface LocateResult {
  seconds: number;
  matches: { bins: string[]; unit: boolean; age: number; at: number }[];
}

export interface AdjustDone {
  action: string;
  before?: number;
  after?: number;
  destination?: string;
  sources?: string[];
}

export interface AdjustResult {
  done: AdjustDone;
  unit: UnitData;
}

export interface AutofillResult {
  layout: Layout;
  added: number;
  found: number;
  parts: Record<string, PartInfo>;
  locations: Record<string, LocationInfo>;
}

export type AdjustAction = 'count' | 'add' | 'remove' | 'move' | 'refill';
