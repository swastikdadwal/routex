import { useEffect, useState } from 'react';
import { SOURCE_NAMES } from '../format.js';

// Saves when the field loses focus or Enter is pressed, and reverts bad input.
function CommitInput({ value, onCommit, type = 'text', min, step, label, className }) {
  const [draft, setDraft] = useState(String(value));
  useEffect(() => setDraft(String(value)), [value]);

  function commit() {
    if (type === 'number') {
      const number = Number(draft);
      if (draft.trim() === '' || !Number.isFinite(number) || (min != null && number < min)) {
        setDraft(String(value));
        return;
      }
      const next = step === 'any' ? number : Math.floor(number);
      setDraft(String(next));
      if (next !== value) onCommit(next);
      return;
    }
    const text = draft.trim();
    if (!text) {
      setDraft(String(value));
      return;
    }
    if (text !== value) onCommit(text);
  }

  return (
    <input
      className={className}
      type={type}
      min={min}
      step={step}
      value={draft}
      aria-label={label}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') event.currentTarget.blur();
      }}
    />
  );
}

// A destructive action asks once, inline, because browser dialogs block the page.
function ConfirmButton({ label, confirmLabel, onConfirm, disabled }) {
  const [asking, setAsking] = useState(false);
  if (!asking) {
    return (
      <button type="button" className="link" disabled={disabled} onClick={() => setAsking(true)}>
        {label}
      </button>
    );
  }
  return (
    <span className="confirm">
      <button
        type="button"
        className="link danger"
        onClick={() => {
          setAsking(false);
          onConfirm();
        }}
      >
        {confirmLabel}
      </button>
      <button type="button" className="link" onClick={() => setAsking(false)}>
        Cancel
      </button>
    </span>
  );
}

export default function ScenarioPanel({
  meta, warehouses, vehicles, orders, warehouseId, setWarehouseId, clickMode, setClickMode,
  actions, settings, setSettings, busy, onRun, onStop,
}) {
  const [city, setCity] = useState('Bengaluru');
  // Eight orders is the largest size where all five algorithms run on three vehicles.
  const [sampleSize, setSampleSize] = useState(8);
  const warehouse = warehouses.find((w) => w.id === warehouseId);
  const active = vehicles.filter((v) => v.active);
  const totalDemand = orders.reduce((sum, o) => sum + o.demand, 0);
  const room = active.reduce((sum, v) => sum + v.capacity, 0);
  const biggest = Math.max(0, ...orders.map((o) => o.demand));
  const largest = Math.max(0, ...active.map((v) => v.capacity));

  let problem = '';
  if (!warehouse) problem = 'Choose or place a warehouse.';
  else if (orders.length === 0) problem = 'Add at least one order.';
  else if (active.length === 0) problem = 'Register at least one active vehicle.';
  else if (active.length > meta.limits.vehicles) problem = `Use at most ${meta.limits.vehicles} active vehicles.`;
  else if (settings.algorithms.length === 0) problem = 'Select at least one algorithm.';

  // Too little capacity does not block a run: the plans report what stays unassigned.
  let shortfall = '';
  if (totalDemand > room) shortfall = `${totalDemand} units ordered but the active fleet carries ${room}. Some orders will stay unassigned.`;
  else if (biggest > largest) shortfall = `An order of ${biggest} units is larger than any active vehicle (${largest}), so it will stay unassigned.`;

  function toggleAlgorithm(id, checked) {
    setSettings((s) => ({
      ...s,
      algorithms: checked ? [...s.algorithms, id] : s.algorithms.filter((a) => a !== id),
    }));
  }

  return (
    <aside className="panel" aria-label="Scenario">
      <section>
        <h2>Sample data</h2>
        <div className="field-row">
          <label className="field grow">
            City
            <select value={city} onChange={(event) => setCity(event.target.value)}>
              {meta.cities.map((c) => <option key={c}>{c}</option>)}
            </select>
          </label>
          <label className="field narrow">
            Orders
            <input
              type="number"
              min="1"
              max={meta.limits.orders}
              value={sampleSize}
              onChange={(event) => setSampleSize(event.target.value)}
            />
          </label>
        </div>
        <button type="button" className="secondary" onClick={() => actions.loadSample(city, Number(sampleSize))}>
          Add sample orders
        </button>
      </section>

      <section>
        <h2>Warehouse</h2>
        {warehouses.length > 0 ? (
          <>
            <select aria-label="Warehouse" value={warehouseId ?? ''} onChange={(event) => setWarehouseId(Number(event.target.value))}>
              {warehouses.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}
            </select>
            {warehouse && (
              <div className="row-actions">
                <CommitInput
                  className="grow"
                  label="Warehouse name"
                  value={warehouse.name}
                  onCommit={(name) => actions.updateWarehouse(warehouse.id, { name })}
                />
                <ConfirmButton label="Delete" confirmLabel="Delete it" onConfirm={() => actions.deleteWarehouse(warehouse.id)} />
              </div>
            )}
          </>
        ) : (
          <p className="hint">No warehouses yet. Add sample orders, or place one on the map.</p>
        )}
      </section>

      <section>
        <h2>Map clicks</h2>
        <div className="segments full" role="group" aria-label="What a map click does">
          <button type="button" aria-pressed={clickMode === 'order'} onClick={() => setClickMode('order')}>Add order</button>
          <button type="button" aria-pressed={clickMode === 'warehouse'} onClick={() => setClickMode('warehouse')}>Place warehouse</button>
        </div>
        <p className="hint">Drag a marker to move it. Right-click an order to remove it.</p>
      </section>

      <section>
        <div className="section-head">
          <h2>Vehicles ({active.length} active)</h2>
          <button type="button" className="link" onClick={actions.addVehicle}>Add vehicle</button>
        </div>
        {vehicles.length > 0 ? (
          <div className="grid-list vehicles">
            <span className="grid-head" aria-hidden="true" />
            <span className="grid-head">Name</span>
            <span className="grid-head">Capacity</span>
            <span className="grid-head">Cost/km</span>
            <span className="grid-head" aria-hidden="true" />
            {vehicles.map((vehicle) => (
              <div className="grid-row" key={vehicle.id}>
                <input
                  type="checkbox"
                  aria-label={`${vehicle.name} active`}
                  checked={vehicle.active}
                  onChange={(event) => actions.updateVehicle(vehicle.id, { active: event.target.checked })}
                />
                <CommitInput label={`${vehicle.name} name`} value={vehicle.name} onCommit={(name) => actions.updateVehicle(vehicle.id, { name })} />
                <CommitInput label={`${vehicle.name} capacity`} type="number" min={1} value={vehicle.capacity} onCommit={(capacity) => actions.updateVehicle(vehicle.id, { capacity })} />
                <CommitInput label={`${vehicle.name} cost per km`} type="number" min={0} step="any" value={vehicle.cost_per_km} onCommit={(cost_per_km) => actions.updateVehicle(vehicle.id, { cost_per_km })} />
                <button type="button" className="remove" aria-label={`Remove ${vehicle.name}`} title="Remove vehicle" onClick={() => actions.deleteVehicle(vehicle.id)}>✕</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">No vehicles registered yet.</p>
        )}
      </section>

      <section>
        <div className="section-head">
          <h2>Orders ({orders.length})</h2>
          {orders.length > 0 && <ConfirmButton label="Clear all" confirmLabel="Clear all orders" onConfirm={actions.clearOrders} />}
        </div>
        {orders.length > 0 ? (
          <div className="grid-list orders">
            <span className="grid-head" aria-hidden="true" />
            <span className="grid-head">Name</span>
            <span className="grid-head">Units</span>
            <span className="grid-head" aria-hidden="true" />
            {orders.map((order, index) => (
              <div className="grid-row" key={order.id}>
                <span className="number">{index + 1}</span>
                <CommitInput label={`Order ${index + 1} name`} value={order.label} onCommit={(label) => actions.updateOrder(order.id, { label })} />
                <CommitInput label={`Order ${index + 1} units`} type="number" min={1} value={order.demand} onCommit={(demand) => actions.updateOrder(order.id, { demand })} />
                <button type="button" className="remove" aria-label={`Remove order ${index + 1}`} title="Remove order" onClick={() => actions.deleteOrder(order.id)}>✕</button>
              </div>
            ))}
          </div>
        ) : (
          <p className="hint">Click the map to add an order.</p>
        )}
      </section>

      <section>
        <h2>Algorithms</h2>
        <div className="checks">
          {meta.algorithms.map((a) => (
            <label key={a.id}>
              <input
                type="checkbox"
                checked={settings.algorithms.includes(a.id)}
                onChange={(event) => toggleAlgorithm(a.id, event.target.checked)}
              />
              {a.name}
            </label>
          ))}
        </div>
        <label className="field">
          Time limit for exact algorithms
          <select
            value={settings.timeLimit}
            onChange={(event) => setSettings((s) => ({ ...s, timeLimit: Number(event.target.value) }))}
          >
            <option value="2">2 seconds</option>
            <option value="10">10 seconds</option>
            <option value="30">30 seconds</option>
            <option value="60">60 seconds</option>
          </select>
        </label>
      </section>

      <section>
        <h2>Distances</h2>
        <div className="checks">
          {Object.entries(SOURCE_NAMES).map(([id, name]) => (
            <label key={id}>
              <input
                type="radio"
                name="source"
                checked={settings.source === id}
                onChange={() => setSettings((s) => ({ ...s, source: id }))}
              />
              {name}
            </label>
          ))}
        </div>
        {settings.source === 'dijkstra' && (
          <p className="hint">The first run in an area downloads its roads, which can take a minute or two.</p>
        )}
      </section>

      <div className="run-bar">
        <p className={problem || shortfall ? 'load-line over' : 'load-line'} role="status">
          {problem || shortfall || `${totalDemand} of ${room} units of fleet capacity used`}
        </p>
        <div className="run-buttons">
          <button type="button" className="primary" disabled={Boolean(problem) || busy} onClick={onRun}>
            {busy ? 'Solving…' : 'Run comparison'}
          </button>
          {busy && <button type="button" className="secondary" onClick={onStop}>Stop</button>}
        </div>
      </div>
    </aside>
  );
}
