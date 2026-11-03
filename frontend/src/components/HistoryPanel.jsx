import { useEffect, useState } from 'react';
import { api } from '../api.js';
import { ACTIVE_RUN_STATES, SOURCE_NAMES, km } from '../format.js';

const STATUS_TEXT = {
  done: 'Finished', cancelled: 'Stopped', failed: 'Failed', pending: 'Running', distances: 'Running', solving: 'Running',
};

export default function HistoryPanel({ activeRunId, onOpen, refreshKey }) {
  const [runs, setRuns] = useState(null);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(null);

  useEffect(() => {
    api.get('/runs').then(setRuns).catch((e) => setError(e.message));
  }, [refreshKey]);

  async function remove(id) {
    setConfirming(null);
    try {
      await api.del(`/runs/${id}`);
      setRuns((list) => list.filter((r) => r.id !== id));
    } catch (e) {
      setError(e.message);
    }
  }

  if (error) return <p className="notice" role="alert">{error}</p>;
  if (!runs) return <div className="empty">Loading…</div>;
  if (runs.length === 0) return <div className="empty">Past comparisons are saved here after you run one.</div>;

  return (
    <div className="table-scroll">
      <table className="data">
        <thead>
          <tr>
            <th>When</th><th>Warehouse</th><th className="num">Orders</th><th className="num">Vehicles</th>
            <th>Distances</th><th className="num">Best distance</th><th>Status</th><th><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const distances = run.results.map((r) => r.distance_m).filter((d) => d != null);
            return (
              <tr key={run.id} className={activeRunId === run.id ? 'selected' : ''}>
                <td className="nowrap">{new Date(run.created_at).toLocaleString()}</td>
                <td>{run.scenario.warehouse.name}</td>
                <td className="num">{run.scenario.orders.length}</td>
                <td className="num">{run.scenario.vehicles.length}</td>
                <td>{SOURCE_NAMES[run.distance_source ?? run.requested_source]}</td>
                <td className="num">{distances.length ? km(Math.min(...distances)) : '–'}</td>
                <td>{STATUS_TEXT[run.status]}</td>
                <td className="nowrap">
                  <button type="button" className="link" onClick={() => onOpen(run)}>Open</button>
                  {' '}
                  {confirming === run.id ? (
                    <span className="confirm">
                      <button type="button" className="link danger" onClick={() => remove(run.id)}>Delete it</button>
                      <button type="button" className="link" onClick={() => setConfirming(null)}>Cancel</button>
                    </span>
                  ) : (
                    <button
                      type="button"
                      className="link"
                      disabled={ACTIVE_RUN_STATES.includes(run.status)}
                      onClick={() => setConfirming(run.id)}
                    >
                      Delete
                    </button>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
