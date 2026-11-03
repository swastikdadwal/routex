import {
  Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Scatter, ScatterChart, Tooltip, XAxis, YAxis,
} from 'recharts';
import {
  ACTIVE_RUN_STATES, SHORT_NAMES, SOURCE_NAMES, formatCount, formatMs, formatTick, isComplete, km, powerTicks, seriesColor,
} from '../format.js';

const ROW_HEIGHT = 40;

function StatusCell({ id, meta, result, stopped }) {
  if (!result) return <span className="muted">{stopped ? 'Stopped' : 'Solving…'}</span>;
  switch (result.status) {
    case 'optimal':
      return <span className="status good"><span className="icon" aria-hidden="true">✓</span>Proven optimal</span>;
    case 'infeasible':
      return <span className="status critical"><span className="icon" aria-hidden="true">▲</span>Proven infeasible</span>;
    case 'incomplete':
      return <span className="status critical"><span className="icon" aria-hidden="true">▲</span>{result.unserved.length} unassigned</span>;
    case 'time_limit':
      return <span className="status warning"><span className="icon" aria-hidden="true">●</span>{result.detail ?? 'Time limit: best found'}</span>;
    case 'skipped':
      return <span className="status neutral">Skipped: {result.detail.charAt(0).toLowerCase() + result.detail.slice(1)}</span>;
    default:
      return (
        <span className="status neutral">
          {id === 'approx' ? 'Tour within 2× of TSP optimum' : meta.limits && 'No guarantee'}
        </span>
      );
  }
}

function headline(run, complete, meta, active) {
  if (complete.length === 0) return active ? 'Solving…' : 'No algorithm produced a complete plan for this scenario.';
  const nameOf = (r) => meta.algorithms.find((a) => a.id === r.algorithm).name;
  const best = complete.reduce((a, b) => (b.distance_m < a.distance_m - 1e-6 ? b : a));
  const exact = complete.filter((r) => r.status === 'optimal');
  if (exact.length === 0) {
    if (active) return `Best plan so far: ${km(best.distance_m)} by ${nameOf(best)}. Still solving…`;
    return `Best plan found: ${km(best.distance_m)} by ${nameOf(best)}. No exact algorithm finished, so it may not be optimal.`;
  }
  const optimum = exact[0].distance_m;
  const quickest = exact.reduce((a, b) => (b.elapsed_ms < a.elapsed_ms ? b : a));
  const others = complete.filter((r) => r.status !== 'optimal');
  const opening = `Optimal plan: ${km(optimum)}, proven by ${nameOf(quickest)} in ${formatMs(quickest.elapsed_ms)}.`;
  if (others.length === 0) return opening;
  const fastest = others.reduce((a, b) => (b.elapsed_ms < a.elapsed_ms ? b : a));
  const gap = ((fastest.distance_m - optimum) / optimum) * 100;
  const quality = gap < 0.005 ? 'and matched the optimum' : `but drove ${gap.toFixed(1)}% farther`;
  return `${opening} ${nameOf(fastest)} answered in ${formatMs(fastest.elapsed_ms)} ${quality}.`;
}

function ChartTip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return <div className="tooltip"><b>{row.name}</b> {row.display}</div>;
}

function DistanceChart({ rows }) {
  return (
    <ResponsiveContainer width="100%" height={rows.length * ROW_HEIGHT + 16}>
      <BarChart layout="vertical" data={rows} margin={{ top: 8, right: 64, bottom: 8, left: 0 }}>
        <XAxis type="number" hide domain={[0, 'dataMax']} />
        <YAxis type="category" dataKey="short" width={64} tickLine={false} axisLine={{ stroke: 'var(--axis)' }} tick={{ fill: 'var(--ink-2)', fontSize: 12 }} />
        <Tooltip content={<ChartTip />} cursor={{ fill: 'var(--sunken)' }} />
        <Bar dataKey="km" fill="var(--series-1)" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
          <LabelList dataKey="km" position="right" formatter={(v) => v.toFixed(2)} style={{ fill: 'var(--ink)', fontSize: 12 }} />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function DotLabel({ x, y, width, height, value }) {
  return (
    <text x={x + width + 6} y={y + height / 2 + 4} fill="var(--ink)" fontSize={11.5}>
      {value}
    </text>
  );
}

// Dots, not bars: a log axis has no zero baseline for bars to grow from.
function TimeChart({ rows }) {
  const ticks = powerTicks(rows.map((r) => r.ms));
  return (
    <ResponsiveContainer width="100%" height={rows.length * ROW_HEIGHT + 44}>
      <ScatterChart margin={{ top: 8, right: 64, bottom: 8, left: 0 }}>
        <CartesianGrid horizontal={false} stroke="var(--grid)" />
        <XAxis
          type="number"
          dataKey="ms"
          scale="log"
          domain={[ticks[0], ticks[ticks.length - 1]]}
          ticks={ticks}
          tickFormatter={formatTick}
          tickLine={false}
          axisLine={{ stroke: 'var(--axis)' }}
          tick={{ fill: 'var(--muted)', fontSize: 11.5 }}
          interval="preserveStartEnd"
        />
        <YAxis type="category" dataKey="short" reversed allowDuplicatedCategory={false} width={64} tickLine={false} axisLine={false} tick={{ fill: 'var(--ink-2)', fontSize: 12 }} />
        <Tooltip content={<ChartTip />} cursor={false} />
        <Scatter data={rows} fill="var(--series-1)" stroke="var(--surface)" strokeWidth={2} isAnimationActive={false}>
          <LabelList dataKey="display" content={DotLabel} />
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

function PathStats({ stats }) {
  const perSearch = (settled, searches) => (searches ? formatCount(Math.round(settled / searches)) : '–');
  return (
    <div className="path-stats">
      <h3>Shortest-path comparison</h3>
      <p className="footnote">
        Road graph of {formatCount(stats.graph_nodes)} junctions and {formatCount(stats.graph_edges)} directed road segments.
        Stops snapped to the nearest connected road, at most {Math.round(stats.largest_snap_m)} m away.
      </p>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Algorithm</th><th>Task</th><th className="num">Searches</th>
              <th className="num">Nodes settled per search</th><th className="num">Total time</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="name">Dijkstra</td><td>One stop to all stops</td>
              <td className="num">{stats.dijkstra_searches}</td>
              <td className="num">{perSearch(stats.dijkstra_settled, stats.dijkstra_searches)}</td>
              <td className="num">{formatMs(stats.dijkstra_ms)}</td>
            </tr>
            <tr>
              <td className="name">A*</td><td>One stop to one stop</td>
              <td className="num">{stats.astar_searches}</td>
              <td className="num">{perSearch(stats.astar_settled, stats.astar_searches)}</td>
              <td className="num">{formatMs(stats.astar_ms)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
}

function PlanTable({ run, result, meta }) {
  const { vehicles, orders } = run.scenario;
  const name = meta.algorithms.find((a) => a.id === result.algorithm).name;
  return (
    <>
      <h3>Delivery plan: {name}</h3>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Vehicle</th><th>Route (order numbers)</th><th className="num">Stops</th>
              <th className="num">Load</th><th className="num">Distance</th><th className="num">Cost</th>
            </tr>
          </thead>
          <tbody>
            {result.routes.map((route) => {
              const vehicle = vehicles[route.vehicle_index];
              return (
                <tr key={route.vehicle_index}>
                  <td className="nowrap">
                    <span className="swatch" style={{ background: seriesColor(route.vehicle_index) }} />
                    {vehicle.name}
                  </td>
                  <td>Warehouse → {route.stops.join(' → ')} → Warehouse</td>
                  <td className="num">{route.stops.length}</td>
                  <td className="num">{route.load} / {vehicle.capacity}</td>
                  <td className="num">{km(route.distance_m)}</td>
                  <td className="num">{route.cost.toFixed(2)}</td>
                </tr>
              );
            })}
            {result.unserved.length > 0 && (
              <tr>
                <td>Unassigned</td>
                <td colSpan="5">Orders {result.unserved.join(', ')} did not fit in this plan.</td>
              </tr>
            )}
            {orders.length > 0 && result.routes.length === 0 && result.unserved.length === 0 && (
              <tr><td colSpan="6">No routes.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </>
  );
}

export default function ResultsPanel({ run, meta, selected }) {
  if (!run) {
    return <div className="empty">Run the comparison to see each algorithm's distance, cost, time and route plan.</div>;
  }
  const active = ACTIVE_RUN_STATES.includes(run.status);
  const stopped = run.status === 'cancelled' || run.status === 'failed';
  const byId = new Map(run.results.map((r) => [r.algorithm, r]));
  const shown = meta.algorithms.filter((a) => run.algorithms.includes(a.id));
  const complete = run.results.filter(isComplete);
  const best = complete.length ? Math.min(...complete.map((r) => r.distance_m)) : null;
  const hasOptimal = complete.some((r) => r.status === 'optimal');
  const rows = shown
    .filter((a) => byId.get(a.id) && isComplete(byId.get(a.id)))
    .map((a) => {
      const r = byId.get(a.id);
      return { id: a.id, name: a.name, short: SHORT_NAMES[a.id], km: r.distance_m / 1000, ms: r.elapsed_ms };
    });
  const selectedResult = byId.get(selected);

  return (
    <div className="results">
      <p className="insight">
        {run.status === 'distances' ? 'Calculating road distances…' : headline(run, complete, meta, active)}
      </p>
      <div className="table-scroll">
        <table className="data">
          <thead>
            <tr>
              <th>Algorithm</th><th className="num">Distance</th>
              <th className="num">{hasOptimal ? 'Above optimum' : 'Above best'}</th>
              <th className="num">Cost</th><th className="num">Vehicles</th>
              <th className="num">Time</th><th className="num">Work</th><th>Result</th>
            </tr>
          </thead>
          <tbody>
            {shown.map((a) => {
              const r = byId.get(a.id);
              const done = r && isComplete(r);
              return (
                <tr key={a.id} className={selected === a.id ? 'selected' : ''}>
                  <td>
                    <span className="name">{a.name}</span>
                    <span className="sub">{a.method} · {a.complexity}</span>
                  </td>
                  <td className="num">{done ? km(r.distance_m) : '–'}</td>
                  <td className="num">{done ? `${(((r.distance_m - best) / best) * 100).toFixed(1)}%` : '–'}</td>
                  <td className="num">{done ? r.cost.toFixed(2) : '–'}</td>
                  <td className="num">{done ? r.routes.length : '–'}</td>
                  <td className="num">{formatMs(r?.elapsed_ms)}</td>
                  <td className="num">
                    {formatCount(r?.work)}
                    {r?.work != null && <span className="sub">{a.work_unit}</span>}
                  </td>
                  <td><StatusCell id={a.id} meta={meta} result={r} stopped={stopped} /></td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="footnote">
        Distances: {SOURCE_NAMES[run.distance_source ?? run.requested_source]}
        {run.distance_source && run.distance_source !== 'straight' && ', averaged over both travel directions'}.
        {' '}Algorithms minimise distance. Each plan's routes then go to the cheapest vehicles that can carry them, and cost is distance times each vehicle's cost per km.
        {!hasOptimal && !active && run.lower_bound_m != null && ` No plan can be shorter than ${km(run.lower_bound_m)} (lower bound).`}
      </p>

      {rows.length > 0 && (
        <div className="chart-row">
          <figure>
            <figcaption>Total distance (km)</figcaption>
            <DistanceChart rows={rows.map((r) => ({ ...r, display: `${r.km.toFixed(2)} km` }))} />
          </figure>
          <figure>
            <figcaption>Execution time (log scale)</figcaption>
            <TimeChart rows={rows.map((r) => ({ ...r, display: formatMs(r.ms) }))} />
          </figure>
        </div>
      )}

      {run.path_stats && <PathStats stats={run.path_stats} />}
      {selectedResult && selectedResult.routes.length > 0 && <PlanTable run={run} result={selectedResult} meta={meta} />}
    </div>
  );
}
