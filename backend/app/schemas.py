from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .algorithms.solvers import ALGORITHM_IDS

Latitude = Field(ge=-90, le=90)
Longitude = Field(ge=-180, le=180)
DistanceSource = Literal["osrm", "dijkstra", "straight"]


class Orm(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class WarehouseIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    lat: float = Latitude
    lng: float = Longitude


class WarehousePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)


class WarehouseOut(Orm):
    id: int
    name: str
    lat: float
    lng: float


class VehicleIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    capacity: int = Field(ge=1, le=100000)
    cost_per_km: float = Field(default=1.0, ge=0, le=100000)
    active: bool = True


class VehiclePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    capacity: int | None = Field(default=None, ge=1, le=100000)
    cost_per_km: float | None = Field(default=None, ge=0, le=100000)
    active: bool | None = None


class VehicleOut(Orm):
    id: int
    name: str
    capacity: int
    cost_per_km: float
    active: bool


class OrderIn(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    lat: float = Latitude
    lng: float = Longitude
    demand: int = Field(default=1, ge=1, le=100000)


class OrderPatch(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=120)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    demand: int | None = Field(default=None, ge=1, le=100000)


class OrderOut(Orm):
    id: int
    label: str
    lat: float
    lng: float
    demand: int


class SampleIn(BaseModel):
    city: str
    orders: int = Field(default=10, ge=1, le=40)
    seed: int | None = None
    replace_orders: bool = False


class RunIn(BaseModel):
    warehouse_id: int
    algorithms: list[Literal[tuple(ALGORITHM_IDS)]] = Field(min_length=1)
    distance_source: DistanceSource = "osrm"
    time_limit_s: float = Field(default=10.0, ge=0.5, le=120)


class OptimizeIn(BaseModel):
    warehouse_id: int
    algorithm: Literal[tuple(ALGORITHM_IDS)]
    distance_source: DistanceSource = "osrm"
    time_limit_s: float = Field(default=10.0, ge=0.5, le=120)


class RunResultOut(Orm):
    algorithm: str
    status: str
    detail: str | None
    distance_m: float | None
    cost: float | None
    elapsed_ms: float | None
    work: int | None
    routes: list
    unserved: list


class RunOut(Orm):
    id: int
    created_at: datetime
    status: str
    scenario: dict
    algorithms: list
    requested_source: str
    distance_source: str | None
    time_limit_s: float
    lower_bound_m: float | None
    path_stats: dict | None
    notice: str | None
    results: list[RunResultOut]


class Point(BaseModel):
    lat: float = Latitude
    lng: float = Longitude


class DistanceMatrixIn(BaseModel):
    points: list[Point] = Field(min_length=2, max_length=41)  # the warehouse plus 40 orders
    source: DistanceSource = "osrm"


class GeometryIn(BaseModel):
    source: DistanceSource
    stops: list[Point] = Field(min_length=2, max_length=60)


class BenchmarkOut(Orm):
    id: int
    created_at: datetime
    status: str
    progress: dict
    config: dict
    rows: list
