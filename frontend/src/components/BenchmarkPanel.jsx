import { useEffect, useState } from 'react';
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { api } from '../api.js';
import { formatMs, formatTick, powerTicks, seriesColor } from '../format.js';

function LineTip({ active, payload, label, format }) {
  if (!active || !payload?.length) return null;
  return (
    <div className="tooltip">
      <div className="tip-title">Orders: {label}</div>
      {payload.map((entry) => (
        <div className="tip-row" key={entry.dataKey}>
          <i style={{ background: entry.color }} />
          <span>{entry.name}</span>
          <b>{format(entry.value)}</b>
        </div>
      ))}
    </div>
  );
}

function SizeChart({ data, series, log, format, tickFormat, ariaLabel }) {
  const values = data.flatMap((row) => series.map((s) => row[s.id]));
  const ticks = log ? powerTicks(values) : undefined;
  return (
    <div role="img" aria-label={ariaLabel}>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 8 }}>
          <CartesianGrid vertical={false} stroke="var(--grid)" />
          <XAxis
            dataKey="n"
            tickLine={false}
            axisLine={{ stroke: 'var(--axis)' }}
            tick={{ fill: 'var(--muted)', fontSize: 11.5 }}
            label={{ value: 'Orders', position: 'insideBottom', offset: -2, fill: 'var(--muted)', fontSize: 11.5 }}
            height={40}
          />
          <YAxis
            scale={log ? 'log' : 'linear'}
            domain={log ? [ticks[0], ticks[ticks.length - 1]] : [0, 'auto']}
            ticks={ticks}
            allowDataOverflow={log}
            tickFormatter={tickFormat}
            tickLine={false}
            axisLine={false}
            width={68}
            tick={{ fill: 'var(--muted)', fontSize: 11.5 }}
          />
          <Tooltip content={<LineTip format={format} />} cursor={{ stroke: 'var(--axis)' }} />
          <Legend verticalAlign="top" align="left" height={52} iconType="plainline" itemSorter={null} wrapperStyle={{ fontSize: 12.5 }} formatter={(name) => <span className="legend-text">{name}</span>} />
          {series.map((s) => (
            <Line
              key={s.id}
              dataKey={s.id}
              name={s.name}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 4, fill: s.color, stroke: 'var(--surface)', strokeWidth: 2 }}
              activeDot={{ r: 6, stroke: 'var(--surface)', strokeWidth: 2 }}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export default function BenchmarkPanel({ meta }) {
  const [benchmark, setBenchmark] = useState(null);
  const [error, setError] = useState('');
  const running = benchmark?.status === 'running';

  useEffect(() => {
    api.get('/benchmarks/latest').then(setBenchmark).catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!running) return undefined;
    const timer = setInterval(() => {
      api.get('/benchmarks/latest').then(setBenchmark).catch((e) => setError(e.message));
    }, 1000);
    return () => clearInterval(timer);
  }, [running]);

  async function toggle() {
    setError('');
    try {
      if (running) setBenchmark(await api.post(`/benchmarks/${benchmark.id}/cancel`));
      else setBenchmark(await api.post('/benchmarks'));
    } catch (e) {
      setError(e.message);
    }
  }

  const rows = benchmark?.rows ?? [];
  const config = benchmark?.config ?? {};
  const series = meta.algorithms.map((a, i) => ({ id: a.id, name: a.name, color: seriesColor(i) }));
  const timeData = rows.map((r) => ({ n: r.n, ...Object.fromEntries(series.map((s) => [s.id, r.algorithms[s.id].ms])) }));
  const gapSeries = series.filter((s) => s.id === 'greedy' || s.id === 'approx' || s.id === 'bnb');
  const gapData = rows.map((r) => ({ n: r.n, ...Object.fromEntries(gapSeries.map((s) => [s.id, r.algorithms[s.id].gap])) }));

  const timeouts = [];
  for (const a of meta.algorithms) {
    const hits = rows.filter((r) => r.algorithms[a.id].timed_out > 0).map((r) => `${r.algorithms[a.id].timed_out}/${config.trials} at ${r.n} orders`);
    if (hits.length) timeouts.push(`${a.name} hit the ${config.time_limit_s} s limit in ${hits.join(', ')}, so its true time there is longer than shown.`);
  }
  const incomplete = rows.reduce((sum, r) => sum + r.algorithms.greedy.incomplete + r.algorithms.approx.incomplete, 0);
  const beyondDp = rows.some((r) => r.n > meta.limits.dp_orders);
  const skippedBrute = rows.filter((r) => r.algorithms.brute.skipped > 0).map((r) => r.n);

  let status = '';
  if (running) {
    const p = benchmark.progress;
    status = p.total ? `Running ${p.n} orders: trial ${p.done} of ${p.total}` : 'Starting…';
  } else if (benchmark?.status === 'done') status = 'Done. Instances are seeded, so a rerun repeats the same inputs.';
  else if (benchmark?.status === 'cancelled') status = 'Stopped. The charts show the sizes that finished.';
  else if (benchmark?.status === 'failed') status = 'The benchmark stopped unexpectedly.';

  return (
    <div className="results">
      <div className="benchmark-head">
        <p>All algorithms solve the same random instances at growing sizes, to show how running time and solution quality change with the number of orders.</p>
        <button type="button" className="primary" onClick={toggle}>{running ? 'Stop benchmark' : 'Run benchmark'}</button>
      </div>
      {error && <p className="notice" role="alert">{error}</p>}
      {status && <p className="footnote" role="status">{status}</p>}
      {rows.length > 0 && (
        <>
          <div className="chart-row wide">
            <figure>
              <figcaption>Mean execution time (log scale)</figcaption>
              <SizeChart
                data={timeData}
                series={series}
                log
                format={formatMs}
                tickFormat={formatTick}
                ariaLabel="Mean execution time against number of orders. The values are in the benchmark data table."
              />
            </figure>
            <figure>
              <figcaption>Mean distance above the optimum (%)</figcaption>
              <SizeChart
                data={gapData}
                series={gapSeries}
                format={(v) => `${v.toFixed(1)}%`}
                tickFormat={(v) => `${v}%`}
                ariaLabel="Mean percentage above the optimal distance against number of orders. The values are in the benchmark data table."
              />
            </figure>
          </div>
          <p className="footnote">
            Mean of {config.trials} random instances per size, {config.vehicles} vehicles with different capacities, straight-line distances.
            {' '}Dynamic Programming and Brute Force are always optimal, so they sit at 0% and are left out of the second chart.
            {beyondDp && ` Dynamic Programming is skipped above ${meta.limits.dp_orders} orders. No optimum is computed there, so the second chart stops at ${meta.limits.dp_orders}.`}
            {skippedBrute.length > 0 && ` Brute Force is skipped at ${skippedBrute.join(', ')} orders because it would have too many plans to check.`}
            {timeouts.length > 0 && ` ${timeouts.join(' ')}`}
            {incomplete > 0 && ` ${incomplete} heuristic runs left orders unassigned and are excluded from the distance chart.`}
          </p>
          <details>
            <summary>Benchmark data table</summary>
            <div className="table-scroll">
              <table className="data">
                <thead>
                  <tr><th className="num">Orders</th><th>Algorithm</th><th className="num">Mean time</th><th className="num">Above optimum</th><th className="num">Timeouts</th></tr>
                </thead>
                <tbody>
                  {rows.flatMap((r) => meta.algorithms.map((a) => {
                    const s = r.algorithms[a.id];
                    return (
                      <tr key={`${r.n}-${a.id}`}>
                        <td className="num">{r.n}</td>
                        <td>{a.name}</td>
                        <td className="num">{s.ms == null ? 'Skipped' : formatMs(s.ms)}</td>
                        <td className="num">{s.gap == null ? 'n/a' : `${s.gap.toFixed(1)}%`}</td>
                        <td className="num">{s.timed_out}</td>
                      </tr>
                    );
                  }))}
                </tbody>
              </table>
            </div>
          </details>
        </>
      )}
    </div>
  );
}
