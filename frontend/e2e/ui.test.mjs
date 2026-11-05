// Drives the whole app in a real browser. See "Tests" in the README for how to run it.
// It deletes everything it finds along the way, so it refuses to run on a database with data in it.
import { chromium } from 'playwright-core';
import fs from 'node:fs';

const BASE = process.env.BASE ?? 'http://127.0.0.1:8099';
const SHOTS = new URL('./shots/', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1');
fs.mkdirSync(SHOTS, { recursive: true });

const results = [];
let section = '';
function check(name, ok, info = '') {
  results.push({ section, name, ok: Boolean(ok), info: String(info) });
  console.log(`${ok ? 'PASS' : 'FAIL'}  [${section}] ${name}${info ? ` -- ${info}` : ''}`);
}
async function step(name, fn) {
  section = name;
  console.log(`\n== ${name}`);
  try {
    await fn();
  } catch (error) {
    check('step finished without an exception', false, error.message.split('\n')[0]);
    await page.screenshot({ path: `${SHOTS}fail-${name.replace(/\W+/g, '_')}.png` }).catch(() => {});
  }
}

const browser = await chromium.launch({ channel: process.env.BROWSER ?? 'chrome', headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
page.setDefaultTimeout(15000);

const consoleErrors = [];
const pageErrors = [];
const badResponses = [];
const failedTiles = [];
let expectBad = false;
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });
page.on('pageerror', (e) => pageErrors.push(e.message));
page.on('response', (r) => {
  const url = r.url();
  if (url.includes('/api/') && r.status() >= 400 && !expectBad) badResponses.push(`${r.status()} ${r.request().method()} ${url}`);
  if (url.includes('tile.openstreetmap.org') && r.status() >= 400) failedTiles.push(`${r.status()} ${url}`);
});

const api = async (path) => (await fetch(`${BASE}/api${path}`)).json();

for (const path of ['/warehouses', '/vehicles', '/orders', '/runs']) {
  if ((await api(path)).length > 0) {
    console.error(`Refusing to run: ${BASE} already has data in ${path}, and this test would delete it.`);
    await browser.close();
    process.exit(2);
  }
}
const btn = (name, exact = true) => page.getByRole('button', { name, exact });
const heading = (re) => page.getByRole('heading', { name: re });
const runBtn = () => btn('Run comparison');
const panel = () => page.locator('section[role=tabpanel]:not([hidden])');
const mainMap = () => page.locator('.map.interactive');
const orderCount = async () => Number((await heading(/^Orders \(/).innerText()).match(/\d+/)[0]);
const settle = () => page.waitForTimeout(500);

async function waitOrders(n) {
  await heading(new RegExp(`^Orders \\(${n}\\)$`)).waitFor({ timeout: 15000 });
}
async function startRun({ source, limit = '10', timeout = 90000 } = {}) {
  if (source) await page.getByLabel(source, { exact: true }).check();
  await page.getByLabel('Time limit for exact algorithms').selectOption(limit);
  const started = Date.now();
  await runBtn().click();
  await page.waitForTimeout(150);
  await runBtn().and(page.locator(':enabled')).waitFor({ timeout });
  await settle();
  return Date.now() - started;
}
function rowsOfResults() {
  return panel().locator('.results > .table-scroll').first().locator('tbody tr');
}
async function clickMapBlank() {
  const box = await mainMap().boundingBox();
  await page.mouse.click(box.x + box.width * 0.55, box.y + box.height * 0.06);
}
const num = (text) => Number(text.replace(/[^\d.]/g, ''));

await step('first load, empty database', async () => {
  const res = await page.goto(BASE);
  check('page returns 200', res.status() === 200);
  await heading(/^RouteX$/).waitFor();
  check('title heading renders', true);
  check('map renders', await mainMap().isVisible());
  check('empty warehouse hint', await page.getByText('No warehouses yet').isVisible());
  check('run blocked with reason', await page.getByText('Choose or place a warehouse.').isVisible());
  check('Run comparison disabled', await runBtn().isDisabled());
  const names = await page.locator('.checks label').allInnerTexts();
  check('all 5 algorithms offered', ['Greedy', 'Dynamic Programming', 'Brute Force', 'Branch and Bound', 'Approximation'].every((a) => names.includes(a)), names.join(', '));
  check('Dijkstra, OSRM and straight-line offered', names.some((n) => /OSRM/.test(n)) && names.some((n) => /Dijkstra/.test(n)) && names.some((n) => /Straight/.test(n)));
  await page.screenshot({ path: `${SHOTS}01-empty.png` });
});

await step('bad input shows a message', async () => {
  expectBad = true;
  await page.getByLabel('Orders', { exact: true }).fill('0');
  await btn('Add sample orders').click();
  await page.locator('.notice').waitFor();
  const zero = await page.locator('.notice').innerText();
  check('sample size 0 says what to enter', /whole number of orders from 1 to 40/.test(zero), zero);
  await page.getByLabel('Orders', { exact: true }).fill('');
  await btn('Add sample orders').click();
  await settle();
  const blank = await page.locator('.notice').innerText();
  check('blank sample size says what to enter', /whole number of orders from 1 to 40/.test(blank), blank);
  await page.getByLabel('Orders', { exact: true }).fill('41');
  await btn('Add sample orders').click();
  await settle();
  check('sample size over the limit says what to enter', /from 1 to 40/.test(await page.locator('.notice').innerText()));
  await page.route('**/api/sample', (route) => route.fulfill({
    status: 422,
    contentType: 'application/json',
    body: JSON.stringify({ detail: [{ msg: 'Input should be a valid city' }] }),
  }));
  await page.getByLabel('Orders', { exact: true }).fill('5');
  await btn('Add sample orders').click();
  await page.getByText('Input should be a valid city').waitFor();
  check('server validation errors show their own message', true);
  await page.unroute('**/api/sample');
  check('nothing was created', (await api('/warehouses')).length === 0 && (await api('/orders')).length === 0);
  expectBad = false;
});

await step('sample data', async () => {
  await page.locator('label.field.grow select').selectOption('Delhi');
  await page.getByLabel('Orders', { exact: true }).fill('6');
  await btn('Add sample orders').click();
  await waitOrders(6);
  check('6 orders listed', true);
  check('6 order markers on map', (await mainMap().locator('.stop').count()) === 6);
  check('warehouse marker on map', (await mainMap().locator('.depot').count()) === 1);
  check('warehouse selected', (await page.getByLabel('Warehouse', { exact: true }).locator('option:checked').innerText()) === 'Delhi warehouse');
  check('3 active vehicles', await heading(/Vehicles \(3 active\)/).isVisible());
  check('previous error cleared', (await page.locator('.notice').count()) === 0);
  check('capacity line shown', await page.getByText(/units of fleet capacity used/).isVisible());
  check('Run comparison enabled', await runBtn().isEnabled());
  await page.waitForTimeout(2500);
  const tiles = await mainMap().locator('img.leaflet-tile').evaluateAll((imgs) => imgs.map((i) => i.complete && i.naturalWidth > 0));
  check('OpenStreetMap tiles load', tiles.length > 0 && tiles.filter(Boolean).length > 0, `${tiles.filter(Boolean).length}/${tiles.length} loaded, ${failedTiles.length} failed`);
  check('OSM attribution shown', await page.getByRole('link', { name: 'OpenStreetMap' }).first().isVisible());
  await page.screenshot({ path: `${SHOTS}02-sample.png` });
});

await step('map editing', async () => {
  const before = await orderCount();
  await clickMapBlank();
  await waitOrders(before + 1);
  check('click on map adds an order', true);
  const stops = mainMap().locator('.stop');
  const orders = await api('/orders');
  const last = orders.at(-1);
  await stops.nth(before).click({ button: 'right' });
  await waitOrders(before);
  check('right-click removes that order', !(await api('/orders')).some((o) => o.id === last.id));

  const first = (await api('/orders'))[0];
  const box = await stops.first().boundingBox();
  await page.mouse.move(box.x + 12, box.y + 12);
  await page.mouse.down();
  await page.mouse.move(box.x + 42, box.y + 32, { steps: 6 });
  await page.mouse.up();
  await settle();
  const moved = (await api('/orders')).find((o) => o.id === first.id);
  check('dragging an order saves its new position', moved.lat !== first.lat && moved.lng !== first.lng);

  const wh = (await api('/warehouses'))[0];
  const hq = await mainMap().locator('.depot').boundingBox();
  await page.mouse.move(hq.x + 14, hq.y + 14);
  await page.mouse.down();
  await page.mouse.move(hq.x + 34, hq.y + 30, { steps: 6 });
  await page.mouse.up();
  await settle();
  const whMoved = (await api('/warehouses'))[0];
  check('dragging the warehouse saves its new position', whMoved.lat !== wh.lat);
});

await step('order and vehicle editing', async () => {
  await page.getByLabel('Order 1 name').fill('Priority drop');
  await page.getByLabel('Order 1 name').press('Enter');
  await settle();
  const o = (await api('/orders'))[0];
  check('order rename saved', o.label === 'Priority drop', o.label);
  const units = page.getByLabel('Order 1 units');
  await units.fill('2');
  await units.press('Enter');
  await settle();
  check('order units saved', (await api('/orders'))[0].demand === 2);
  await units.fill('-4');
  await units.press('Enter');
  await settle();
  check('invalid units revert', (await units.inputValue()) === '2' && (await api('/orders'))[0].demand === 2, await units.inputValue());
  await page.getByLabel('Order 1 name').fill('   ');
  await page.getByLabel('Order 1 name').press('Tab');
  await settle();
  check('blank name reverts', (await api('/orders'))[0].label === 'Priority drop');

  await btn('Add vehicle').click();
  await heading(/Vehicles \(4 active\)/).waitFor();
  check('add vehicle', true);
  await page.getByLabel('New vehicle capacity').fill('25');
  await page.getByLabel('New vehicle capacity').press('Enter');
  await settle();
  await page.getByLabel('New vehicle cost per km').fill('3.5');
  await page.getByLabel('New vehicle cost per km').press('Enter');
  await settle();
  const nv = (await api('/vehicles')).find((v) => v.name === 'New vehicle');
  check('vehicle capacity and cost saved', nv.capacity === 25 && nv.cost_per_km === 3.5, JSON.stringify(nv));
  await page.getByLabel('New vehicle active').click();
  await heading(/Vehicles \(3 active\)/).waitFor();
  check('deactivate vehicle', true);
  await btn('Remove New vehicle').click();
  await settle();
  check('remove vehicle', (await api('/vehicles')).length === 3);

  for (const a of ['Greedy', 'Dynamic Programming', 'Brute Force', 'Branch and Bound', 'Approximation']) await page.getByLabel(a).uncheck();
  check('no algorithms blocks the run', (await page.getByText('Select at least one algorithm.').isVisible()) && (await runBtn().isDisabled()));
  for (const a of ['Greedy', 'Dynamic Programming', 'Brute Force', 'Branch and Bound', 'Approximation']) await page.getByLabel(a).check();
  check('run enabled again', await runBtn().isEnabled());
});

async function verifyFullRun(tag, label) {
  const runs = await api('/runs');
  const latest = runs.sort((a, b) => b.id - a.id)[0];
  check('run finished', latest.status === 'done', `status=${latest.status} source=${latest.distance_source} notice=${latest.notice ?? ''}`);
  check(`distances really came from ${label}`, latest.distance_source === label, latest.distance_source);
  const rows = rowsOfResults();
  check('5 result rows', (await rows.count()) === 5);
  const byAlgo = {};
  for (const name of ['Greedy', 'Dynamic Programming', 'Brute Force', 'Branch and Bound', 'Approximation']) {
    const cells = await rows.filter({ hasText: name }).first().locator('td').allInnerTexts();
    byAlgo[name] = { distance: num(cells[1]), cost: num(cells[3]), result: cells[7] };
  }
  const exact = ['Dynamic Programming', 'Brute Force', 'Branch and Bound'];
  check('exact solvers proven optimal', exact.every((a) => /Proven optimal/.test(byAlgo[a].result)), exact.map((a) => byAlgo[a].result).join(' | '));
  check('exact solvers agree on distance', new Set(exact.map((a) => byAlgo[a].distance)).size === 1, exact.map((a) => byAlgo[a].distance).join(', '));
  check('heuristics are never below the optimum', byAlgo.Greedy.distance >= byAlgo['Brute Force'].distance && byAlgo.Approximation.distance >= byAlgo['Brute Force'].distance, `greedy ${byAlgo.Greedy.distance}, approx ${byAlgo.Approximation.distance}, optimal ${byAlgo['Brute Force'].distance}`);
  const apiGreedy = latest.results.find((r) => r.algorithm === 'greedy');
  check('table figures match the API', Math.abs(byAlgo.Greedy.distance - apiGreedy.distance_m / 1000) < 0.01 && Math.abs(byAlgo.Greedy.cost - apiGreedy.cost) < 0.01);
  check('headline names the optimum', /Optimal plan:/.test(await panel().locator('.insight').innerText()), await panel().locator('.insight').innerText());
  const charts = panel().locator('.chart-row figure');
  check('distance and time charts render', (await charts.count()) === 2 && (await charts.nth(0).locator('svg.recharts-surface').count()) >= 1 && (await charts.nth(1).locator('svg.recharts-surface').count()) >= 1);
  check('distance chart has a bar per algorithm', (await charts.nth(0).locator('.recharts-bar-rectangle').count()) === 5, await charts.nth(0).locator('.recharts-bar-rectangle').count());
  check('time chart has a dot per algorithm', (await charts.nth(1).locator('.recharts-scatter-symbol').count()) === 5, await charts.nth(1).locator('.recharts-scatter-symbol').count());
  return latest;
}

await step('run comparison: straight line', async () => {
  const ms = await startRun({ source: 'Straight line' });
  check('finishes quickly', ms < 20000, `${ms} ms`);
  const latest = await verifyFullRun('straight', 'straight');
  const best = latest.results.find((r) => r.algorithm === 'dp');
  check('route lines drawn, one per vehicle used', (await mainMap().locator('path.leaflet-interactive').count()) === best.routes.length, `${await mainMap().locator('path.leaflet-interactive').count()} lines, ${best.routes.length} routes`);
  check('legend lists vehicles', (await page.locator('.map-legend .legend-item').count()) === best.routes.length + 1);
  const plan = panel().locator('.table-scroll').nth(1).locator('tbody tr');
  check('plan table has a row per route', (await plan.count()) === best.routes.length);
  await page.screenshot({ path: `${SHOTS}03-straight.png`, fullPage: true });

  const group = page.getByRole('group', { name: 'Algorithm shown on the map' });
  await group.getByRole('button', { name: /Greedy/ }).click();
  await heading(/Delivery plan: Greedy/).waitFor();
  check('switching algorithm changes the plan', true);
  const greedy = latest.results.find((r) => r.algorithm === 'greedy');
  check('map follows the selected plan', (await mainMap().locator('path.leaflet-interactive').count()) === greedy.routes.length);
  await settle();
  for (const r of latest.results) {
    const served = r.routes.flatMap((x) => x.stops).sort((a, b) => a - b);
    check(`${r.algorithm}: every order delivered exactly once`, served.join() === latest.scenario.orders.map((_, i) => i + 1).join(), served.join());
    const vehicles = latest.scenario.vehicles;
    check(`${r.algorithm}: no vehicle over capacity`, r.routes.every((x) => x.load <= vehicles[x.vehicle_index].capacity));
  }

  await btn('Compare all').click();
  await page.locator('.compare-card').first().waitFor();
  check('compare view shows 5 cards', (await page.locator('.compare-card').count()) === 5);
  check('compare view shows 5 maps', (await page.locator('.compare-map .map').count()) === 5);
  await page.waitForTimeout(1500);
  await page.screenshot({ path: `${SHOTS}04-compare.png`, fullPage: true });
  await btn('Single map').click();
  await mainMap().waitFor();
  check('back to single map', true);
});

await step('editing clears stale results', async () => {
  await clickMapBlank();
  await page.waitForTimeout(800);
  check('results reset after an edit', await page.getByText('Run the comparison to see each algorithm').isVisible());
  check('route lines removed after an edit', (await mainMap().locator('path.leaflet-interactive').count()) === 0);
  const n = await orderCount();
  await btn(`Remove order ${n}`).click();
  await waitOrders(n - 1);
});

await step('run comparison: OSRM road network', async () => {
  const geometry = [];
  const on = (r) => { if (r.url().endsWith('/api/geometry')) geometry.push(r.status()); };
  page.on('response', on);
  await startRun({ source: 'OSRM road network', timeout: 90000 });
  await verifyFullRun('osrm', 'osrm');
  await page.waitForTimeout(4000);
  page.off('response', on);
  check('road geometry fetched for the map', geometry.length > 0 && geometry.every((s) => s === 200), geometry.join());
  const pts = await mainMap().locator('path.leaflet-interactive').first().getAttribute('d');
  check('route follows roads, not straight lines', (pts.match(/L/g) ?? []).length > 10, `${(pts.match(/L/g) ?? []).length} segments`);
  check('footnote names the source', await page.getByText(/Distances: OSRM road network/).isVisible());
  await page.screenshot({ path: `${SHOTS}05-osrm.png`, fullPage: true });
});

await step('run comparison: Dijkstra on OpenStreetMap roads', async () => {
  await page.getByLabel('Dijkstra on OpenStreetMap roads').check();
  check('download warning shown', await page.getByText(/downloads its roads/).isVisible());
  const ms = await startRun({ timeout: 280000 });
  const latest = (await api('/runs')).sort((a, b) => b.id - a.id)[0];
  check('finished', latest.status === 'done', `${(ms / 1000).toFixed(0)} s, used=${latest.distance_source}, notice=${latest.notice ?? 'none'}`);
  check('Dijkstra really used, no fallback', latest.distance_source === 'dijkstra', `used=${latest.distance_source} notice=${latest.notice ?? ''}`);
  if (latest.distance_source === 'dijkstra') {
    await verifyFullRun('dijkstra', 'dijkstra');
    check('Dijkstra vs A* table shown', await page.getByRole('heading', { name: 'Shortest-path comparison' }).isVisible());
    const s = latest.path_stats;
    check('A* settles fewer nodes than Dijkstra', s.astar_settled / s.astar_searches < s.dijkstra_settled / s.dijkstra_searches, `A* ${Math.round(s.astar_settled / s.astar_searches)} vs Dijkstra ${Math.round(s.dijkstra_settled / s.dijkstra_searches)} per search`);
  }
  await page.screenshot({ path: `${SHOTS}06-dijkstra.png`, fullPage: true });
});

await step('not enough capacity', async () => {
  const names = (await api('/vehicles')).map((v) => v.name);
  const saved = (await api('/vehicles')).map((v) => v.capacity);
  for (const n of names) {
    await page.getByLabel(`${n} capacity`).fill('1');
    await page.getByLabel(`${n} capacity`).press('Enter');
    await page.waitForTimeout(250);
  }
  check('shortfall warning shown', await page.getByText(/Some orders will stay unassigned|stay unassigned/).isVisible());
  await startRun({ source: 'Straight line' });
  const text = await rowsOfResults().allInnerTexts();
  check('algorithms report the problem, none claims success', text.every((t) => /unassigned|infeasible/i.test(t)), text.map((t) => t.split('\n').pop()).join(' | '));
  check('headline admits no complete plan', /No algorithm produced a complete plan/.test(await panel().locator('.insight').innerText()));
  await page.screenshot({ path: `${SHOTS}07-capacity.png`, fullPage: true });
  for (let i = 0; i < names.length; i += 1) {
    await page.getByLabel(`${names[i]} capacity`).fill(String(saved[i] + 60));
    await page.getByLabel(`${names[i]} capacity`).press('Enter');
    await page.waitForTimeout(250);
  }
});

await step('large scenario, time limit and Stop', async () => {
  await page.locator('label.field.grow select').selectOption('Delhi');
  await page.getByLabel('Orders', { exact: true }).fill('20');
  await btn('Add sample orders').click();
  await waitOrders(26);
  const ms = await startRun({ source: 'Straight line', limit: '2', timeout: 60000 });
  check('2 s limit respected', ms < 15000, `${ms} ms`);
  const row = async (name) => (await rowsOfResults().filter({ hasText: name }).first().innerText()).replace(/\s+/g, ' ');
  check('DP skipped above its limit', /Skipped/.test(await row('Dynamic Programming')));
  check('Brute Force skipped', /Skipped/.test(await row('Brute Force')));
  check('Branch and Bound reports time limit, not optimal', !/Proven optimal/.test(await row('Branch and Bound')), (await row('Branch and Bound')).slice(-60));
  check('headline does not claim an optimum', /may not be optimal|Best plan/.test(await panel().locator('.insight').innerText()), await panel().locator('.insight').innerText());
  await page.screenshot({ path: `${SHOTS}08-large.png`, fullPage: true });

  await page.getByLabel('Time limit for exact algorithms').selectOption('60');
  const t0 = Date.now();
  await runBtn().click();
  await btn('Stop').waitFor();
  check('Solving state and Stop button shown', await btn('Solving…').isDisabled());
  await page.waitForTimeout(1500);
  await btn('Stop').click();
  await runBtn().and(page.locator(':enabled')).waitFor({ timeout: 20000 });
  const took = Date.now() - t0;
  check('Stop ends a 60 s search early', took < 15000, `${took} ms`);
  const latest = (await api('/runs')).sort((a, b) => b.id - a.id)[0];
  check('run marked as stopped', latest.status === 'cancelled', latest.status);
});

await step('history', async () => {
  await page.getByRole('tab', { name: 'History' }).click();
  await panel().locator('tbody tr').first().waitFor();
  const runs = await api('/runs');
  const rows = panel().locator('tbody tr');
  check('every run listed', (await rows.count()) === runs.length, `${await rows.count()} rows, ${runs.length} runs`);
  await page.screenshot({ path: `${SHOTS}09-history.png`, fullPage: true });

  const osrm = runs.find((r) => r.distance_source === 'osrm');
  const row = rows.filter({ hasText: 'OSRM road network' }).first();
  await row.getByRole('button', { name: 'Open' }).click();
  await panel().locator('.results .insight').waitFor();
  check('opening a past run shows its results', /Optimal plan/.test(await panel().locator('.insight').innerText()));
  check('opened run shows its own orders', (await mainMap().locator('.stop').count()) === osrm.scenario.orders.length, `${await mainMap().locator('.stop').count()} markers, ${osrm.scenario.orders.length} orders`);

  await page.getByRole('tab', { name: 'History' }).click();
  await panel().locator('tbody tr').first().waitFor();
  const r0 = panel().locator('tbody tr').last();
  await r0.getByRole('button', { name: 'Delete', exact: true }).click();
  await r0.getByRole('button', { name: 'Cancel' }).click();
  check('delete can be cancelled', (await api('/runs')).length === runs.length);
  await r0.getByRole('button', { name: 'Delete', exact: true }).click();
  await r0.getByRole('button', { name: 'Delete it' }).click();
  await settle();
  check('delete removes the run', (await api('/runs')).length === runs.length - 1);
  check('table updates after delete', (await panel().locator('tbody tr').count()) === runs.length - 1);
});

await step('scaling benchmark', async () => {
  await page.getByRole('tab', { name: 'Scaling benchmark' }).click();
  await btn('Run benchmark').click();
  await btn('Stop benchmark').waitFor();
  check('benchmark starts, Stop offered', true);
  const t0 = Date.now();
  let status = '';
  while (Date.now() - t0 < 200000) {
    const b = await api('/benchmarks/latest');
    status = b.status;
    if (status !== 'running') break;
    await page.waitForTimeout(2000);
  }
  const finished = status === 'done';
  const secs = ((Date.now() - t0) / 1000).toFixed(0);
  check('benchmark finished within 200 s', finished, `status=${status} after ${secs} s`);
  if (!finished) {
    await btn('Stop benchmark').click();
    await page.getByText(/Stopped\. The charts show/).waitFor({ timeout: 30000 });
    check('Stop works', true);
  }
  await page.waitForTimeout(1500);
  const b = await api('/benchmarks/latest');
  check('benchmark produced rows', b.rows.length > 0, `${b.rows.length} sizes: ${b.rows.map((r) => r.n).join(', ')}`);
  check('two line charts render', (await panel().locator('.chart-row figure svg.recharts-surface').count()) >= 2);
  check('time chart draws 5 series', (await panel().locator('.chart-row figure').first().locator('.recharts-line-curve').count()) === 5, await panel().locator('.chart-row figure').first().locator('.recharts-line-curve').count());
  await panel().getByText('Benchmark data table').click();
  check('data table has a row per size and algorithm', (await panel().locator('details tbody tr').count()) === b.rows.length * 5);
  await page.screenshot({ path: `${SHOTS}10-benchmark.png`, fullPage: true });

  const first = b.rows[0].algorithms;
  check('exact solvers at 0% above optimum', first.dp.gap === 0 && (first.brute.gap ?? 0) === 0, `dp ${first.dp.gap}, brute ${first.brute.gap}, bnb ${first.bnb.gap}`);
  const dpRows = b.rows.filter((r) => r.algorithms.brute.ms != null && r.algorithms.greedy.ms != null);
  if (dpRows.length >= 2) {
    const a = dpRows[0].algorithms.brute.ms; const z = dpRows.at(-1).algorithms.brute.ms;
    check('Brute Force time grows with size', z > a, `${a.toFixed(2)} ms to ${z.toFixed(2)} ms`);
  }
  if (finished) {
    await btn('Run benchmark').click();
    await btn('Stop benchmark').waitFor();
    await page.waitForTimeout(1000);
    await btn('Stop benchmark').click();
    await page.getByText(/Stopped\. The charts show/).waitFor({ timeout: 30000 });
    check('Stop works', true);
  }
  await page.getByRole('tab', { name: 'Results' }).click();
});

await step('reload keeps data', async () => {
  const before = (await api('/orders')).length;
  await page.reload();
  await heading(/^RouteX$/).waitFor();
  await waitOrders(before);
  check('orders still listed after reload', true);
  check('markers restored', (await mainMap().locator('.stop').count()) === before);
  await page.getByRole('tab', { name: 'History' }).click();
  await panel().locator('tbody tr').first().waitFor();
  check('history still listed after reload', (await panel().locator('tbody tr').count()) === (await api('/runs')).length);
  await page.getByRole('tab', { name: 'Results' }).click();
});

await step('sample in a second city', async () => {
  const n = await orderCount();
  const runsBefore = (await api('/runs')).length;
  await page.locator('label.field.grow select').selectOption('London');
  await page.getByLabel('Orders', { exact: true }).fill('3');
  await btn('Add sample orders').click();
  await btn('Replace orders').waitFor();
  check('asks before mixing cities', await page.getByText(/too far to plan together/).isVisible());
  check('nothing changed while asking', (await api('/orders')).length === n);
  await page.screenshot({ path: `${SHOTS}11-replace-prompt.png` });
  await btn('Cancel').click();
  check('cancel keeps the orders', (await orderCount()) === n && (await btn('Add sample orders').isVisible()));

  await btn('Add sample orders').click();
  await page.locator('label.field.grow select').selectOption('Paris');
  check('changing city closes the question', await btn('Add sample orders').isVisible());
  await page.locator('label.field.grow select').selectOption('London');
  await btn('Add sample orders').click();
  await btn('Replace orders').click();
  await waitOrders(3);
  const orders = await api('/orders');
  const spanLat = Math.max(...orders.map((o) => o.lat)) - Math.min(...orders.map((o) => o.lat));
  check('replacing leaves one city', spanLat < 1, `latitude span ${spanLat.toFixed(2)} degrees`);
  check('new warehouse selected', (await page.getByLabel('Warehouse', { exact: true }).locator('option:checked').innerText()) === 'London warehouse');
  check('past runs kept', (await api('/runs')).length === runsBefore);

  await startRun({ source: 'Straight line' });
  const latest = (await api('/runs')).sort((a, b) => b.id - a.id)[0];
  const dp = latest.results.find((r) => r.algorithm === 'dp');
  check('the replaced scenario plans normally', dp.status === 'optimal' && dp.distance_m < 200000, `${dp.status}, ${(dp.distance_m / 1000).toFixed(1)} km`);

  await page.getByLabel('Orders', { exact: true }).fill('2');
  await btn('Add sample orders').click();
  await waitOrders(5);
  check('adding in the same city does not ask', true);
});

await step('order limit', async () => {
  expectBad = true;
  const room = 40 - (await orderCount());
  await page.getByLabel('Orders', { exact: true }).fill(String(room + 1));
  await btn('Add sample orders').click();
  await page.locator('.notice').waitFor();
  const text = await page.locator('.notice').innerText();
  check('over-limit sample explained', /more orders fit/.test(text), text);
  expectBad = false;
});

await step('warehouses and clearing', async () => {
  await btn('Clear all').click();
  await btn('Cancel').click();
  check('clear can be cancelled', (await orderCount()) > 0);
  await btn('Clear all').click();
  await btn('Clear all orders').click();
  await waitOrders(0);
  check('clear removes all orders', (await api('/orders')).length === 0);
  check('run blocked with no orders', await page.getByText('Add at least one order.').isVisible());

  const count = (await api('/warehouses')).length;
  await btn('Place warehouse').click();
  await clickMapBlank();
  await settle();
  const all = await api('/warehouses');
  check('Place warehouse adds one', all.length === count + 1, all.at(-1)?.name);
  check('click mode returns to Add order', (await btn('Add order').getAttribute('aria-pressed')) === 'true');
  await page.getByLabel('Warehouse name').fill('Main depot');
  await page.getByLabel('Warehouse name').press('Enter');
  await settle();
  check('warehouse rename saved', (await api('/warehouses')).at(-1).name === 'Main depot');
  check('warehouse dropdown updates', (await page.getByLabel('Warehouse', { exact: true }).locator('option:checked').innerText()) === 'Main depot');

  const left = (await api('/warehouses')).length;
  for (let i = 0; i < left; i += 1) {
    await btn('Delete').click();
    await btn('Delete it').click();
    await settle();
  }
  check('warehouses can all be deleted', (await api('/warehouses')).length === 0);
  check('run blocked with no warehouse', await page.getByText('Choose or place a warehouse.').isVisible());
  check('past runs survive warehouse deletion', (await api('/runs')).length > 0);
  check('no crash, app still rendered', await heading(/^RouteX$/).isVisible());

  for (const v of await api('/vehicles')) await btn(`Remove ${v.name}`).click({ timeout: 5000 }).then(settle);
  check('vehicles can all be removed', (await api('/vehicles')).length === 0);
});

await step('page quality', async () => {
  const text = await page.locator('body').innerText();
  check('no garbled characters on the page', !/â€|Ã|ï¿½/.test(text));
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(800);
  const m = await page.evaluate(() => ({ s: document.documentElement.scrollWidth, c: document.documentElement.clientWidth }));
  check('no sideways scrolling on a phone', m.s <= m.c + 1, `${m.s} vs ${m.c}`);
  await page.screenshot({ path: `${SHOTS}12-phone.png` });
  await page.setViewportSize({ width: 1440, height: 1000 });

  check('no JavaScript exceptions in the whole session', pageErrors.length === 0, pageErrors.slice(0, 3).join(' || '));
  const realConsole = consoleErrors.filter((t) => !/Failed to load resource/.test(t));
  check('no console errors in the whole session', realConsole.length === 0, realConsole.slice(0, 3).join(' || '));
  check('no unexpected API errors in the whole session', badResponses.length === 0, [...new Set(badResponses)].slice(0, 5).join(' || '));
  check('no failed map tiles', failedTiles.length === 0, `${failedTiles.length}; ${failedTiles[0] ?? ''}`);
});

await browser.close();
const failed = results.filter((r) => !r.ok);
fs.writeFileSync(`${SHOTS}results.json`, JSON.stringify(results, null, 1));
console.log(`\n==== ${results.length - failed.length} passed, ${failed.length} failed of ${results.length}`);
for (const f of failed) console.log(`FAILED [${f.section}] ${f.name} -- ${f.info}`);
process.exit(failed.length ? 1 : 0);
