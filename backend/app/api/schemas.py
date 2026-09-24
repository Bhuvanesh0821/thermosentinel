"""Pydantic models documenting the API contract in OpenAPI (/api/docs)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class Meta(BaseModel):
    model_config = ConfigDict(extra="allow")
    generated_at: datetime


class ApiResponse(BaseModel, Generic[T]):
    status: Literal["ok"] = "ok"
    data: T
    meta: Meta


class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None


class ApiError(BaseModel):
    status: Literal["error"] = "error"
    error: ErrorBody


ERROR_RESPONSES = {
    400: {"model": ApiError, "description": "Invalid request"},
    404: {"model": ApiError, "description": "Not found"},
    422: {"model": ApiError, "description": "Validation error"},
    503: {"model": ApiError, "description": "Database not configured or unreachable"},
}


class Feature(BaseModel):
    type: Literal["Feature"] = "Feature"
    id: int | str | None = None
    geometry: dict[str, Any] | None
    properties: dict[str, Any]


class FeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[Feature]


class Observation(BaseModel):
    id: int
    source_id: str
    source_mode: str
    product: str
    instrument: str
    satellite: str | None
    satellite_name: str | None
    latitude: float
    longitude: float
    brightness: float | None
    brightness_2: float | None
    frp: float | None
    scan: float | None
    track: float | None
    acq_date: date
    acq_time: str
    acquired_at: datetime
    confidence_raw: str | None
    confidence_level: str | None
    confidence_pct: int | None
    daynight: str | None
    version: str | None
    cluster_id: int | None
    ingestion_run_id: int | None
    ingested_at: datetime


class Facility(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    source_id: str
    source_ref: str
    source_url: str | None
    name: str | None
    facility_type: str
    facility_type_label: str
    facility_subtype: str | None
    operator: str | None
    website: str | None
    latitude: float
    longitude: float
    footprint_area_m2: float | None
    source_timestamp: datetime | None


class Cluster(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    status: str
    center_latitude: float
    center_longitude: float
    observation_count: int
    max_frp: float | None
    avg_frp: float | None
    start_time: datetime
    end_time: datetime
    persistence_category: str | None
    spatial_relationship: str | None
    industrial_association: bool
    nearest_facility_distance_m: float | None
    facility_name: str | None
    classification: str | None
    classification_label: str | None
    evidence_strength: str | None
    risk_score: float | None
    priority: str | None
    incident_id: int | None


class Incident(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    reference: str
    cluster_id: int
    facility_id: int | None
    title: str
    classification: str
    classification_label: str
    priority: str
    risk_score: float
    status: str
    latitude: float
    longitude: float
    first_detected_at: datetime
    last_detected_at: datetime
    observation_count: int
    max_frp: float | None
    summary: str | None


class AlertLocation(BaseModel):
    latitude: float
    longitude: float


class AlertFacility(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    name: str | None
    type: str | None


class Alert(BaseModel):
    model_config = ConfigDict(extra="allow")
    alert_id: int
    incident_id: int | None
    created_at: datetime
    severity: str
    status: str
    title: str
    description: str
    rules: list[str]
    location: AlertLocation | None
    facility: AlertFacility | None
    source: str
    last_triggered_at: datetime
    acknowledged_at: datetime | None
    resolved_at: datetime | None


class Notification(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: int
    alert_id: int | None
    channel: str
    title: str
    body: str
    status: str
    created_at: datetime
    read_at: datetime | None


class DataSource(BaseModel):
    model_config = ConfigDict(extra="allow")
    id: str
    name: str
    category: str
    provider: str
    license: str | None
    status: str
    status_message: str | None
    last_success_at: datetime | None
    last_attempt_at: datetime | None


class Health(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str
    version: str
    environment: str
    time: datetime
    database: dict[str, Any]
    firms_mode: str
    scheduler: dict[str, Any]
    pipeline: dict[str, Any]
