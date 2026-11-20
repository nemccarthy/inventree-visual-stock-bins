import type { InvenTreePluginContext } from '@inventreedb/ui';
import {
  ActionIcon,
  Alert,
  Anchor,
  Badge,
  Button,
  Center,
  Group,
  Indicator,
  Loader,
  SegmentedControl,
  Stack,
  Text,
  Tooltip
} from '@mantine/core';
import {
  IconAlertTriangle,
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconCircleX,
  IconClipboardCheck,
  IconFlag,
  IconLayoutGrid,
  IconPencil,
  IconRefresh,
  IconTruckLoading
} from '@tabler/icons-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

import { Bench, type ShowMode, fitUnit, frameChrome } from './Bench';
import { BinDrawer } from './BinDrawer';
import { CountWalk } from './CountWalk';
import { Editor } from './Editor';
import { RefillList } from './RefillList';
import {
  apiData,
  apiError,
  apiUrl,
  fmtQty,
  fmtTime,
  locationUrl,
  plural
} from './format';
import type { Layout, LocateResult, UnitData, UnitResult } from './types';
import { AppLink, usePageVisible, useStyles, useWidth } from './ui';

const EMPTY_LAYOUT: Layout = {
  version: 1,
  kind: 'bench',
  product: null,
  rows: [{ id: 'r1', name: '', columns: [] }]
};

function Legend({ product }: Readonly<{ product: boolean }>) {
  const swatch = (style: React.CSSProperties) => (
    <span
      style={{
        display: 'inline-block',
        width: 12,
        height: 12,
        borderRadius: 3,
        verticalAlign: -2,
        marginRight: 5,
        boxSizing: 'border-box',
        ...style
      }}
    />
  );

  return (
    <Group gap='md' c='dimmed' fz='xs'>
      <span>
        {swatch({
          border: '1px solid var(--mantine-color-default-border)',
          background:
            'linear-gradient(to top, var(--mantine-color-teal-light-hover) 60%, transparent 60%)'
        })}
        Level in the bin
      </span>
      <span>
        <IconAlertTriangle size={13} color='var(--mantine-color-yellow-filled)' style={{ verticalAlign: -2, marginRight: 4 }} />
        Below minimum
      </span>
      <span>
        <IconCircleX size={13} color='var(--mantine-color-red-filled)' style={{ verticalAlign: -2, marginRight: 4 }} />
        Empty
      </span>
      {product && (
        <span>
          <IconFlag size={13} color='var(--mantine-color-orange-filled)' style={{ verticalAlign: -2, marginRight: 4 }} />
          Runs out first
        </span>
      )}
    </Group>
  );
}

/** One unit: the drawing of its bins, with counting, refilling and the layout editor */
export function UnitView({
  context,
  locationId,
  variant,
  startFull = false,
  onChanged
}: Readonly<{
  context: InvenTreePluginContext;
  locationId: number;
  /** 'panel' on a stock location page, 'page' on the Bins page */
  variant: 'panel' | 'page';
  startFull?: boolean;
  /** Called when the layout is saved or removed */
  onChanged?: () => void;
}>) {
  useStyles();

  const api = useRef(context.api);
  api.current = context.api;

  const [result, setResult] = useState<UnitResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [counting, setCounting] = useState(false);
  const [refilling, setRefilling] = useState(false);
  const [full, setFull] = useState(startFull);
  const [mode, setMode] = useState<ShowMode>('quantity');
  const [flashing, setFlashing] = useState<Set<string>>(new Set());
  const [flashUnit, setFlashUnit] = useState(false);
  const [spot, setSpot] = useState<Set<string> | null>(null);
  const [areaRef, areaWidth] = useWidth<HTMLDivElement>();
  const visible = usePageVisible();

  const load = useCallback(
    (quiet = false) => {
      if (!quiet) {
        setLoading(true);
      }

      return api.current
        .get(apiUrl(`unit/${locationId}/`))
        .then((response) => {
          setResult(apiData<UnitResult>(response, 'configured'));
          setError(null);
        })
        .catch((err) => {
          // A refresh in the background which fails keeps what is on screen
          if (!quiet) {
            setError(apiError(err, 'Could not load the bins'));
          }
        })
        .finally(() => setLoading(false));
    },
    [locationId]
  );

  useEffect(() => {
    setResult(null);
    setEditing(false);
    setSelected(null);
    setCounting(false);
    setRefilling(false);
    load();
  }, [load]);

  const unit: UnitData | null = result?.configured ? result : null;
  const idle = !editing && !counting && !refilling && selected === null;
  const refresh = unit?.settings.refresh_seconds ?? 0;

  // Reload the stock levels while the view is open and nothing is being changed
  useEffect(() => {
    if (!unit || !idle || !visible || refresh <= 0) {
      return;
    }

    const timer = window.setInterval(() => load(true), Math.max(5, refresh) * 1000);

    return () => window.clearInterval(timer);
  }, [unit !== null, idle, visible, refresh, load]);

  // Flash the bins which somebody has just asked InvenTree to locate
  useEffect(() => {
    if (!unit || editing || !visible) {
      setFlashing(new Set());
      setFlashUnit(false);
      return;
    }

    let cancelled = false;

    const poll = () => {
      api.current
        .get(apiUrl('locate/'), { params: { unit: locationId } })
        .then((response) => {
          if (cancelled) {
            return;
          }

          const data = apiData<LocateResult>(response, 'matches');
          const ids = new Set<string>();

          data.matches.forEach((match) => match.bins.forEach((id) => ids.add(id)));

          setFlashing((previous) =>
            previous.size === ids.size && [...ids].every((id) => previous.has(id)) ? previous : ids
          );
          setFlashUnit(data.matches.some((match) => match.unit));
        })
        .catch(() => undefined);
    };

    poll();

    const timer = window.setInterval(poll, 4000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [unit !== null, editing, visible, locationId]);

  // When nothing has been open on top of the drawing since
  const idleSince = useRef(Number.POSITIVE_INFINITY);

  useEffect(() => {
    idleSince.current = idle ? performance.now() : Number.POSITIVE_INFINITY;
  }, [idle]);

  // Full window: Escape leaves it, and the page behind does not scroll
  useEffect(() => {
    if (!full) {
      return;
    }

    const onKey = (event: KeyboardEvent) => {
      // The Escape which closes a bin or a dialog must not also leave the full
      // window: only a key pressed after that was closed counts
      if (event.key === 'Escape' && event.timeStamp > idleSince.current) {
        setFull(false);
      }
    };

    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKey);

    return () => {
      document.body.style.overflow = previous;
      window.removeEventListener('keydown', onKey);
    };
  }, [full]);

  const u = useMemo(() => {
    if (!unit) {
      return 84;
    }

    return fitUnit(unit.layout, areaWidth, 0, frameChrome(unit.layout.kind) + 4);
  }, [unit?.layout, areaWidth]);

  const limited = useMemo(() => new Set(unit?.buildable?.limited_by ?? []), [unit?.buildable]);
  const due = useMemo(
    () => (unit ? Object.values(unit.bins).filter((item) => item.refill > 0).length : 0),
    [unit?.bins]
  );

  if (!result) {
    return error ? (
      <Alert color='red' title='Could not load the bins'>
        {error}
      </Alert>
    ) : (
      <Center h={200}>
        <Loader />
      </Center>
    );
  }

  const location = result.location;
  const canEdit = result.permissions.layout;

  if (editing) {
    return (
      <div className={full ? 'vb-full' : undefined}>
        <Editor
          context={context}
          location={location}
          initial={unit ? unit.layout : EMPTY_LAYOUT}
          bins={unit?.bins}
          product={unit?.product}
          configured={!!unit}
          onSaved={(saved) => {
            setResult(saved);
            setEditing(false);
            onChanged?.();
          }}
          onCancel={() => setEditing(false)}
          onDeleted={() => {
            setEditing(false);
            load();
            onChanged?.();
          }}
        />
      </div>
    );
  }

  if (!unit) {
    const setup = result.configured ? null : result.setup;

    return (
      <Stack align='center' gap='sm' py='xl'>
        <IconLayoutGrid size={40} color='var(--mantine-color-dimmed)' />
        <Text fw={700} fz='lg'>
          Draw the bins of {location.name}
        </Text>
        <Text size='sm' c='dimmed' ta='center' maw={520}>
          Lay out the bins of this bench or shelving unit the way they look from the front. Each
          bin then shows its stock level, and can be counted and topped up from the drawing.
        </Text>
        {setup && (setup.parts > 0 || setup.children > 0) && (
          <Text size='sm' c='dimmed'>
            {[
              setup.parts > 0 ? `${plural(setup.parts, 'part')} stocked here` : '',
              setup.children > 0 ? `${plural(setup.children, 'location')} below it` : ''
            ]
              .filter(Boolean)
              .join(', ')}
            : bins can be made from either.
          </Text>
        )}
        {canEdit ? (
          <Button leftSection={<IconPencil size={16} />} onClick={() => setEditing(true)}>
            Set up bins
          </Button>
        ) : (
          <Text size='sm' c='dimmed'>
            Somebody who may change stock locations can set this up.
          </Text>
        )}
      </Stack>
    );
  }

  const summary = unit.summary;
  const limitedNames = unit.buildable
    ? unit.buildable.limited_by
        .map((id) => ({ id, title: unit.bins[id]?.title ?? '' }))
        .filter((entry, index, list) => list.findIndex((other) => other.title === entry.title) === index)
    : [];

  const body = (
    <Stack gap='sm'>
      <Group justify='space-between' align='flex-start' gap='sm'>
        <div style={{ minWidth: 0 }}>
          {(variant === 'page' || full) && (
            <Group gap='xs' align='baseline'>
              <Text fw={700} fz='xl' lh={1.2}>
                {location.name}
              </Text>
              {!full && (
                <AppLink context={context} to={locationUrl(location.pk)} size='xs'>
                  {location.pathstring}
                </AppLink>
              )}
            </Group>
          )}
          <Group gap={6} mt={variant === 'page' || full ? 6 : 0}>
            {summary.empty > 0 && (
              <Badge
                color='red'
                variant='light'
                radius='sm'
                style={{ cursor: 'pointer' }}
                onClick={() =>
                  setSpot(new Set(Object.values(unit.bins).filter((item) => item.status === 'empty').map((item) => item.id)))
                }
              >
                {summary.empty} empty
              </Badge>
            )}
            {summary.low > 0 && (
              <Badge
                color='yellow'
                variant='light'
                radius='sm'
                style={{ cursor: 'pointer' }}
                onClick={() =>
                  setSpot(new Set(Object.values(unit.bins).filter((item) => item.status === 'low').map((item) => item.id)))
                }
              >
                {summary.low} below minimum
              </Badge>
            )}
            <Badge color='teal' variant='light' radius='sm'>
              {summary.ok} OK
            </Badge>
            {spot && (
              <Anchor component='button' type='button' size='xs' onClick={() => setSpot(null)}>
                Show all
              </Anchor>
            )}
          </Group>
          {unit.product && unit.buildable && (
            <Text size='sm' mt={6}>
              Enough for <b>{fmtQty(unit.buildable.units)}</b> × {unit.product.name}
              {limitedNames.length > 0 && (
                <Text span c='dimmed' size='sm'>
                  {' '}
                  · runs out first:{' '}
                  {limitedNames.map((entry, index) => (
                    <span key={entry.id}>
                      {index > 0 ? ', ' : ''}
                      <Anchor component='button' type='button' size='sm' onClick={() => setSelected(entry.id)}>
                        {entry.title}
                      </Anchor>
                    </span>
                  ))}
                </Text>
              )}
            </Text>
          )}
          {unit.product && !unit.buildable && (
            <Text size='sm' c='dimmed' mt={6}>
              None of the bins holds a part of {unit.product.name}.
            </Text>
          )}
        </div>

        <Group gap='xs' wrap='wrap' justify='flex-end'>
          {unit.product && (
            <SegmentedControl
              size='xs'
              data={[
                { value: 'quantity', label: 'Quantity' },
                { value: 'covers', label: 'Units covered' }
              ]}
              value={mode}
              onChange={(next) => setMode(next as ShowMode)}
            />
          )}
          {unit.permissions.adjust && (
            <Button
              variant='default'
              size='xs'
              leftSection={<IconClipboardCheck size={15} />}
              onClick={() => setCounting(true)}
            >
              Count
            </Button>
          )}
          <Indicator label={due} size={16} disabled={due === 0} color='red' offset={4}>
            <Button
              variant='default'
              size='xs'
              leftSection={<IconTruckLoading size={15} />}
              onClick={() => setRefilling(true)}
            >
              Refill
            </Button>
          </Indicator>
          {canEdit && (
            <Button
              variant='default'
              size='xs'
              leftSection={<IconPencil size={15} />}
              onClick={() => {
                setSelected(null);
                setEditing(true);
              }}
            >
              Edit layout
            </Button>
          )}
          <Tooltip label={`Updated ${fmtTime(unit.generated)}. Refresh`} openDelay={300}>
            <ActionIcon variant='default' size={30} aria-label='Refresh' loading={loading} onClick={() => load()}>
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
          <Tooltip label={full ? 'Leave full window (Esc)' : 'Full window'} openDelay={300}>
            <ActionIcon
              variant='default'
              size={30}
              aria-label={full ? 'Leave full window' : 'Full window'}
              onClick={() => setFull((value) => !value)}
            >
              {full ? <IconArrowsMinimize size={16} /> : <IconArrowsMaximize size={16} />}
            </ActionIcon>
          </Tooltip>
        </Group>
      </Group>

      {error && (
        <Alert color='red' p='xs'>
          {error}
        </Alert>
      )}

      <div ref={areaRef} style={{ overflowX: 'auto', padding: '6px 2px 10px' }}>
        {summary.bins === 0 ? (
          <Text size='sm' c='dimmed' py='lg'>
            This layout has no bins yet.{canEdit ? ' Use "Edit layout" to add some.' : ''}
          </Text>
        ) : (
          <Bench
            layout={unit.layout}
            bins={unit.bins}
            u={u}
            mode={mode}
            selected={selected}
            flashing={flashing}
            flashUnit={flashUnit}
            limited={limited}
            dimOthers={spot}
            showImages={unit.settings.show_images}
            onSelect={setSelected}
          />
        )}
      </div>

      <Group justify='space-between'>
        <Legend product={!!unit.product} />
        <Text size='xs' c='dimmed'>
          {flashing.size > 0 || flashUnit ? 'Locating… ' : ''}
          Updated {fmtTime(unit.generated)}
          {refresh > 0 ? `, every ${refresh} s` : ''}
        </Text>
      </Group>

      <BinDrawer
        context={context}
        unit={unit}
        binId={selected}
        onClose={() => setSelected(null)}
        onUnit={setResult}
      />
      <CountWalk
        context={context}
        unit={unit}
        opened={counting}
        onClose={() => setCounting(false)}
        onUnit={setResult}
      />
      <RefillList
        context={context}
        unit={unit}
        opened={refilling}
        onClose={() => setRefilling(false)}
        onUnit={setResult}
      />
    </Stack>
  );

  // Always the same wrapper, so that going full window does not rebuild what is inside
  return <div className={full ? 'vb-full' : undefined}>{body}</div>;
}
