import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api.js';
import { ACTIVE_RUN_STATES, SHORT_NAMES, isComplete, km, seriesColor } from './format.js';
import BenchmarkPanel from './components/BenchmarkPanel.jsx';
import HistoryPanel from './components/HistoryPanel.jsx';
import ResultsPanel from './components/ResultsPanel.jsx';
import RouteMap from './components/RouteMap.jsx';
import ScenarioPanel from './components/ScenarioPanel.jsx';

const TABS = [['run', 'Results'], ['benchmark', 'Scaling benchmark'], ['history', 'History']];

function bestResult(results) {
  const complete = results.filter(isComplete);
  if (complete.length) return complete.reduce((a, b) => (b.distance_m < a.distance_m - 1e-6 ? b : a));
  return results.find((r) => r.routes.length > 0) ?? null;
}

export default function App() {
  const [meta, setMeta] = useState(null);
  const [warehouses, setWarehouses] = useState([]);
  const [vehicles, setVehicles] = useState([]);
  const [orders, setOrders] = useState([]);
  const [warehouseId, setWarehouseId] = useState(null);
  const [settings, setSettings] = useState({ algorithms: [], source: 'osrm', timeLimit: 10 });
  const [clickMode, setClickMode] = useState('order');
  const [run, setRun] = useState(null);
  const [selected, setSelected] = useState(null);
  const [userSelected, setUserSelected] = useState(false);
  const [view, setView] = useState('single');
  const [tab, setTab] = useState('run');
  const [notice, setNotice] = useState('');
  const [fitKey, setFitKey] = useState(0);
  const [historyKey, setHistoryKey] = useState(0);

  const busy = Boolean(run && ACTIVE_RUN_STATES.includes(run.status));

  const report = useCallback((error) => setNotice(error.message), []);

  useEffect(() => {
    Promise.all([api.get('/meta'), api.get('/warehouses'), api.get('/vehicles'), api.get('/orders')])
      .then(([metaData, warehouseData, vehicleData, orderData]) => {
        setMeta(metaData);
        setSettings((s) => ({ ...s, algorithms: metaData.algorithms.map((a) => a.id) }));
        setWarehouses(warehouseData);
        setVehicles(vehicleData);
        setOrders(orderData);
        setWarehouseId(warehouseData.at(-1)?.id ?? null);
        setFitKey((k) => k + 1);
      })
      .catch(report);
  }, [report]);

  // An edit means the shown routes no longer describe the map. The run itself
  // stays saved in History, as a snapshot of the scenario it solved.
  const scenarioChanged = useCallback(() => {
    setRun((current) => {
      if (current && ACTIVE_RUN_STATES.includes(current.status)) api.post(`/runs/${current.id}/cancel`).catch(() => {});
      return null;
    });
    setSelected(null);
    setUserSelected(false);
    setNotice('');
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const timer = setInterval(() => {
      api.get(`/runs/${run.id}`)
        .then((latest) => {
          // A newer action may have replaced this run while the request was out.
          setRun((current) => (current?.id === latest.id ? latest : current));
        })
        .catch(report);
    }, 400);
    return () => clearInterval(timer);
  }, [busy, run?.id, report]);

  useEffect(() => {
    if (!run) return;
    if (run.notice) setNotice(run.notice);
    if (userSelected) return;
    const best = bestResult(run.results);
    if (best) setSelected(best.algorithm);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run]);

  const actions = useMemo(() => {
    const guard = (fn) => async (...args) => {
      try {
        await fn(...args);
      } catch (error) {
        report(error);
      }
    };
    return {
      loadSample: guard(async (city, count) => {
        const { warehouse_id: newId } = await api.post('/sample', { city, orders: count });
        const [w, v, o] = await Promise.all([api.get('/warehouses'), api.get('/vehicles'), api.get('/orders')]);
        setWarehouses(w);
        setVehicles(v);
        setOrders(o);
        setWarehouseId(newId);
        scenarioChanged();
        setFitKey((k) => k + 1);
      }),
      addVehicle: guard(async () => {
        const created = await api.post('/vehicles', { name: 'New vehicle', capacity: 10, cost_per_km: 1 });
        setVehicles((list) => [...list, created]);
        scenarioChanged();
      }),
      updateVehicle: guard(async (id, patch) => {
        const updated = await api.patch(`/vehicles/${id}`, patch);
        setVehicles((list) => list.map((v) => (v.id === id ? updated : v)));
        scenarioChanged();
      }),
      deleteVehicle: guard(async (id) => {
        await api.del(`/vehicles/${id}`);
        setVehicles((list) => list.filter((v) => v.id !== id));
        scenarioChanged();
      }),
      addOrder: guard(async ({ lat, lng }) => {
        const created = await api.post('/orders', { lat, lng, demand: 1 });
        setOrders((list) => [...list, created]);
        scenarioChanged();
      }),
      updateOrder: guard(async (id, patch) => {
        const updated = await api.patch(`/orders/${id}`, patch);
        setOrders((list) => list.map((o) => (o.id === id ? updated : o)));
        scenarioChanged();
      }),
      deleteOrder: guard(async (id) => {
        await api.del(`/orders/${id}`);
        setOrders((list) => list.filter((o) => o.id !== id));
        scenarioChanged();
      }),
      clearOrders: guard(async () => {
        await api.del('/orders');
        setOrders([]);
        scenarioChanged();
      }),
      placeWarehouse: guard(async ({ lat, lng }, name) => {
        const created = await api.post('/warehouses', { name, lat, lng });
        setWarehouses((list) => [...list, created]);
        setWarehouseId(created.id);
        scenarioChanged();
      }),
      updateWarehouse: guard(async (id, patch) => {
        const updated = await api.patch(`/warehouses/${id}`, patch);
        setWarehouses((list) => list.map((w) => (w.id === id ? updated : w)));
        scenarioChanged();
      }),
      deleteWarehouse: guard(async (id) => {
        await api.del(`/warehouses/${id}`);
        setWarehouses((list) => {
          const remaining = list.filter((w) => w.id !== id);
          setWarehouseId(remaining.at(-1)?.id ?? null);
          return remaining;
        });
        scenarioChanged();
      }),
    };
  }, [report, scenarioChanged]);

  const onMapClick = useCallback((latlng) => {
    if (clickMode === 'warehouse') {
      actions.placeWarehouse(latlng, `Warehouse ${warehouses.length + 1}`);
      setClickMode('order');
    } else {
      actions.addOrder(latlng);
    }
  }, [actions, clickMode, warehouses.length]);

  async function startRun() {
    setNotice('');
    setSelected(null);
    setUserSelected(false);
    setTab('run');
    try {
      const created = await api.post('/runs', {
        warehouse_id: warehouseId,
        algorithms: settings.algorithms,
        distance_source: settings.source,
        time_limit_s: settings.timeLimit,
      });
      setRun(created);
      setHistoryKey((k) => k + 1);
    } catch (error) {
      report(error);
    }
  }

  async function stopRun() {
    try {
      await api.post(`/runs/${run.id}/cancel`);
    } catch (error) {
      report(error);
    }
  }

  function openFromHistory(past) {
    setRun(past);
    setUserSelected(false);
    setSelected(bestResult(past.results)?.algorithm ?? null);
    setNotice(past.notice ?? '');
    setTab('run');
    setFitKey((k) => k + 1);
  }

  if (!meta) {
    return <div className="empty" role="status">{notice || 'Loading RouteX…'}</div>;
  }

  const liveWarehouse = warehouses.find((w) => w.id === warehouseId) ?? null;
  const scenario = run ? run.scenario : { warehouse: liveWarehouse, orders, vehicles };
  const source = run?.distance_source ?? 'straight';
  const byId = new Map((run?.results ?? []).map((r) => [r.algorithm, r]));
  const selectedResult = byId.get(selected) ?? null;
  const shownAlgorithms = meta.algorithms.filter((a) => (run ? run.algorithms.includes(a.id) : settings.algorithms.includes(a.id)));
  const routed = selectedResult?.routes ?? [];

  return (
    <>
      <header className="topbar">
        <h1>RouteX</h1>
        <p>Which vehicle delivers each order, and by which route, to minimise total distance</p>
      </header>
      <div className="layout">
        <ScenarioPanel
          meta={meta}
          warehouses={warehouses}
          vehicles={vehicles}
          orders={orders}
          warehouseId={warehouseId}
          setWarehouseId={(id) => {
            setWarehouseId(id);
            scenarioChanged();
            setFitKey((k) => k + 1);
          }}
          clickMode={clickMode}
          setClickMode={setClickMode}
          actions={actions}
          settings={settings}
          setSettings={setSettings}
          busy={busy}
          onRun={startRun}
          onStop={stopRun}
        />
        <main>
          <div className="map-toolbar">
            <div className="segments" role="group" aria-label="Algorithm shown on the map">
              {shownAlgorithms.map((a) => {
                const result = byId.get(a.id);
                const usable = result && result.routes.length > 0;
                return (
                  <button
                    key={a.id}
                    type="button"
                    aria-pressed={selected === a.id}
                    disabled={!usable}
                    onClick={() => {
                      setSelected(a.id);
                      setUserSelected(true);
                    }}
                  >
                    {SHORT_NAMES[a.id]}
                    {result && isComplete(result) && <small>{km(result.distance_m)}</small>}
                  </button>
                );
              })}
            </div>
            <div className="segments" role="group" aria-label="Map layout">
              <button type="button" aria-pressed={view === 'single'} onClick={() => setView('single')}>Single map</button>
              <button type="button" aria-pressed={view === 'compare'} onClick={() => setView('compare')}>Compare all</button>
            </div>
          </div>
          {notice && <div className="notice" role="status">{notice}</div>}

          {view === 'single' ? (
            <div className="map-wrap">
              <RouteMap
                interactive
                scenario={scenario}
                result={selectedResult}
                source={source}
                fitKey={fitKey}
                onMapClick={onMapClick}
                onMoveOrder={(id, { lat, lng }) => actions.updateOrder(id, { lat, lng })}
                onDeleteOrder={actions.deleteOrder}
                onMoveWarehouse={(id, { lat, lng }) => actions.updateWarehouse(id, { lat, lng })}
              />
              {routed.length > 0 && (
                <div className="map-legend">
                  {routed.map((route) => (
                    <span className="legend-item" key={route.vehicle_index}>
                      <i style={{ background: seriesColor(route.vehicle_index) }} />
                      {scenario.vehicles[route.vehicle_index].name}
                    </span>
                  ))}
                  <span className="legend-item">HQ: warehouse</span>
                </div>
              )}
            </div>
          ) : (
            <div className="compare-grid">
              {shownAlgorithms.map((a) => {
                const result = byId.get(a.id);
                const value = result && isComplete(result) ? km(result.distance_m) : '';
                const hasPlan = result && result.routes.length > 0;
                let message = 'Run the comparison to see this plan.';
                if (result?.status === 'skipped') message = `Skipped: ${result.detail}`;
                else if (result) message = 'No plan to show.';
                else if (busy) message = 'Solving…';
                return (
                  <article className="compare-card" key={a.id}>
                    <header>{a.name}<span>{value}</span></header>
                    {hasPlan
                      ? <div className="compare-map"><RouteMap scenario={scenario} result={result} source={source} fitKey={`${fitKey}-${run.id}`} /></div>
                      : <div className="compare-empty">{message}</div>}
                  </article>
                );
              })}
            </div>
          )}

          <div className="tabs" role="tablist">
            {TABS.map(([id, label]) => (
              <button key={id} type="button" role="tab" aria-selected={tab === id} onClick={() => setTab(id)}>{label}</button>
            ))}
          </div>
          <section role="tabpanel" hidden={tab !== 'run'}>
            <ResultsPanel run={run} meta={meta} selected={selected} />
          </section>
          {tab === 'benchmark' && <section role="tabpanel"><BenchmarkPanel meta={meta} /></section>}
          {tab === 'history' && (
            <section role="tabpanel">
              <HistoryPanel activeRunId={run?.id} onOpen={openFromHistory} refreshKey={`${historyKey}-${run?.status}`} />
            </section>
          )}
        </main>
      </div>
    </>
  );
}
