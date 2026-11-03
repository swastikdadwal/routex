# RouteX

Intelligent multi-vehicle delivery route optimization. RouteX decides which vehicle delivers each order and which route that vehicle follows to minimise total distance. It solves the same problem (the capacitated vehicle routing problem) with five algorithm design techniques and compares them on real-world maps, to show the trade-off between computational efficiency and solution quality.

## Technology

| Layer | Technology |
|---|---|
| Frontend | React, Recharts |
| Backend | Python, FastAPI |
| Database | PostgreSQL |
| Maps | Leaflet, OpenStreetMap |
| Road routing | OSRM, plus Dijkstra and A* on OpenStreetMap road data |

## Set up and run

You need [Python 3.11+](https://www.python.org/downloads/), [Node.js](https://nodejs.org/) and [PostgreSQL 17](https://www.postgresql.org/download/). These steps are for Windows PowerShell.

If PowerShell blocks the scripts, run them with `powershell -ExecutionPolicy Bypass -File .\setup.ps1`.

```powershell
.\setup.ps1
.\start.ps1
```

`setup.ps1` runs once. It asks for the password you chose for PostgreSQL's `postgres` user, creates the database, and builds the frontend. It stores its settings in `backend\.env`, which Git ignores.

`start.ps1` opens the app at http://localhost:8000. You need an internet connection for map tiles and road data.

## Using RouteX

1. Select **Add sample orders**, or use **Place warehouse** and click the map to build your own scenario.
2. Add, edit or remove vehicles and orders in the side panel. Everything is saved to the database. Drag map markers to move them, and right-click an order to remove it.
3. Choose the algorithms and distance source, then select **Run comparison**.
4. Switch between plans above the map, or use **Compare all** to see them side by side.
5. Open **Scaling benchmark** to see how time and quality change as orders grow, or **History** to reopen past runs.

## Algorithms

Here n is the number of orders and m the number of vehicles.

| Technique | Method | Time | Result quality |
|---|---|---|---|
| Greedy | Nearest neighbour, filling one vehicle at a time | O(n²) | No guarantee |
| Dynamic Programming | Held–Karp TSP for each subset of orders, then the best partition of subsets across vehicles | O(2ⁿn² + m·3ⁿ) | Optimal. Limited to 13 orders |
| Brute Force | Every order sequence and vehicle split, with no pruning on cost | O(n!·C(n+m−1, m−1)) | Optimal. Limited to 3 million plans, which is 8 orders on 3 vehicles |
| Branch and Bound | Depth-first search, pruned with a minimum spanning tree bound and symmetry breaking | O(n!) worst case | Optimal if it finishes within the time limit, otherwise the best plan found |
| Approximation | Double-tree tour from a minimum spanning tree, then the cheapest capacity split over every tour rotation | O(m·n³) | The tour is within 2× of the optimal single-vehicle tour on metric distances. Splitting adds warehouse trips, so 2× is not a bound on the final fleet plan |

### Shortest paths

Choose **Dijkstra on OpenStreetMap roads** to calculate road distances inside RouteX rather than through OSRM. RouteX downloads the area's roads, builds a directed graph that respects one-way streets, and runs Dijkstra between stops. It also runs A* on the same stop pairs and shows both algorithms' work side by side.

The two road sources give different totals because they answer different questions. Dijkstra finds the shortest road distance, while OSRM reports the distance along the fastest route.

## Limits and assumptions

- An order cannot be split across vehicles.
- If the fleet cannot carry every order, a run still goes ahead. Greedy and Approximation return a partial plan and list the unassigned orders. The exact algorithms report that no complete plan exists, because they do not search for the best partial plan.
- Algorithms minimise distance first. Each plan's routes then go to the cheapest vehicles that can carry them, which lowers cost without changing distance. Distance and cost are not optimised jointly, so the shortest plan is not always the cheapest possible plan when vehicles have different rates.
- Time windows and traffic are not modelled.
- A comparison takes up to 40 orders and 8 active vehicles.
- Road distances are averaged over both travel directions, because the solvers need a symmetric matrix. Fastest-route distances can slightly break the triangle inequality that the 2× bound relies on.
- Timings come from Python, measured in a separate process. Compare them with each other, not with other languages.
- OSRM, Overpass and OpenStreetMap tiles are free public services meant for light use, and stop locations are sent to them. If road data is unavailable, a run falls back to straight-line distances and says so.

## API

All routes sit under `/api`. Interactive documentation is at http://localhost:8000/docs.

| Endpoint | Purpose |
|---|---|
| `POST /orders`, `GET /orders` | Add and retrieve delivery orders |
| `POST /vehicles`, `GET /vehicles` | Register and retrieve vehicles |
| `POST /distance-matrix` | Calculate distances between points |
| `POST /optimize` | Run one algorithm on the saved scenario |
| `POST /compare` | Run several algorithms on the saved scenario |
| `GET /results` | Retrieve past runs |
| `GET /runs/{id}` | Poll one run, since runs finish in the background |

## Tests

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
```

The tests check DP, Branch and Bound and Brute Force against an independent exhaustive solver, and Dijkstra and A* against Bellman-Ford. API tests run full comparisons on a separate `routex_test` database.

## Project layout

```
setup.ps1, start.ps1           one-time setup and start scripts
backend/app/algorithms/        one module per technique: greedy, dynamic_programming,
                               brute_force, branch_bound, approximation
                               solvers.py runs them; shortest_path.py has Dijkstra and A*
backend/app/road_data.py       OSRM, Overpass, distance matrices, route geometry
backend/app/runner.py          background runs, saved to the database as they finish
backend/app/solver_process.py  child process that runs solvers and the benchmark
backend/app/main.py            FastAPI routes
backend/app/models.py          PostgreSQL tables
backend/scripts/init_db.py     creates the database and writes backend/.env
backend/tests/                 algorithm, road data and API tests
frontend/src/                  React app
```

For frontend development, keep the backend running and use `npm run dev` in `frontend`, then open http://localhost:5173.
