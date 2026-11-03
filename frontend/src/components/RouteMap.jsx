import { useEffect, useMemo, useState } from 'react';
import L from 'leaflet';
import { MapContainer, Marker, Polyline, TileLayer, useMap, useMapEvents } from 'react-leaflet';
import { routeGeometry } from '../api.js';
import { seriesColor, seriesInk } from '../format.js';

const ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const DEFAULT_CENTER = [20.5937, 78.9629];

function stopIcon(label, vehicleIndex, unserved) {
  const style = vehicleIndex == null ? '' : `--stop:${seriesColor(vehicleIndex)};--stop-ink:${seriesInk(vehicleIndex)}`;
  return L.divIcon({
    className: `stop${unserved ? ' unserved' : ''}`,
    html: `<span style="${style}">${label}</span>`,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

const warehouseIcon = L.divIcon({
  className: 'depot',
  html: '<span>HQ</span>',
  iconSize: [28, 28],
  iconAnchor: [14, 14],
});

function FitToPoints({ fitKey, points }) {
  const map = useMap();
  useEffect(() => {
    if (points.length === 1) map.setView([points[0].lat, points[0].lng], 13);
    if (points.length > 1) map.fitBounds(L.latLngBounds(points.map((p) => [p.lat, p.lng])).pad(0.12));
    // Refit only when the scenario identity changes, not on each small edit.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);
  return null;
}

function ClickHandler({ onClick }) {
  useMapEvents({ click: (event) => onClick(event.latlng) });
  return null;
}

function RouteLine({ stops, source, color }) {
  const straight = useMemo(() => stops.map((p) => [p.lat, p.lng]), [stops]);
  const [road, setRoad] = useState(null);
  useEffect(() => {
    let current = true;
    setRoad(null);
    if (source !== 'straight') {
      routeGeometry(source, stops).then((line) => {
        if (current && line) setRoad(line);
      });
    }
    return () => {
      current = false;
    };
  }, [source, stops]);
  return <Polyline positions={road ?? straight} pathOptions={{ color, weight: 4, opacity: 0.9 }} />;
}

// scenario: { warehouse, orders, vehicles }. result is optional, and its routes
// colour the stops. Handlers are only passed for the editable map.
export default function RouteMap({ scenario, result, source, fitKey, interactive, onMapClick, onMoveOrder, onDeleteOrder, onMoveWarehouse }) {
  const { warehouse, orders } = scenario;
  const vehicleOfStop = new Map();
  result?.routes.forEach((route) => route.stops.forEach((stop) => vehicleOfStop.set(stop, route.vehicle_index)));
  const unserved = new Set(result?.unserved ?? []);
  const points = warehouse ? [warehouse, ...orders] : orders;

  const routes = useMemo(() => {
    if (!result || !warehouse) return [];
    return result.routes.map((route) => ({
      vehicleIndex: route.vehicle_index,
      stops: [warehouse, ...route.stops.map((stop) => orders[stop - 1]), warehouse],
    }));
  }, [result, warehouse, orders]);

  return (
    <MapContainer
      center={DEFAULT_CENTER}
      zoom={5}
      className={interactive ? 'map interactive' : 'map'}
      zoomControl={interactive}
      dragging={interactive}
      scrollWheelZoom={interactive}
      doubleClickZoom={interactive}
      boxZoom={interactive}
      touchZoom={interactive}
      keyboard={interactive}
      zoomSnap={interactive ? 1 : 0.25}
    >
      <TileLayer url="https://tile.openstreetmap.org/{z}/{x}/{y}.png" maxZoom={19} attribution={ATTRIBUTION} />
      <FitToPoints fitKey={fitKey} points={points} />
      {interactive && <ClickHandler onClick={onMapClick} />}
      {routes.map((route) => (
        <RouteLine key={route.vehicleIndex} stops={route.stops} source={source} color={seriesColor(route.vehicleIndex)} />
      ))}
      {orders.map((order, index) => (
        <Marker
          key={order.id}
          position={[order.lat, order.lng]}
          icon={stopIcon(index + 1, vehicleOfStop.get(index + 1), unserved.has(index + 1))}
          draggable={interactive}
          interactive={interactive}
          keyboard={interactive}
          title={interactive ? `${order.label}: ${order.demand} units` : ''}
          alt={order.label}
          eventHandlers={
            interactive
              ? {
                  dragend: (event) => onMoveOrder(order.id, event.target.getLatLng()),
                  contextmenu: () => onDeleteOrder(order.id),
                }
              : undefined
          }
        />
      ))}
      {warehouse && (
        <Marker
          position={[warehouse.lat, warehouse.lng]}
          icon={warehouseIcon}
          draggable={interactive}
          interactive={interactive}
          keyboard={interactive}
          title={interactive ? warehouse.name : ''}
          alt={warehouse.name}
          zIndexOffset={1000}
          eventHandlers={interactive ? { dragend: (event) => onMoveWarehouse(warehouse.id, event.target.getLatLng()) } : undefined}
        />
      )}
    </MapContainer>
  );
}
