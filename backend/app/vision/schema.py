"""The job draft a photo produces. Shaped so the invoice step can turn ``lines``
straight into JobLine rows (kind, description, qty, unit_cents, part_id)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# Below this a field is read back to the owner before anything is invoiced.
CHECK_BELOW = 0.75


class DraftField(BaseModel):
    value: Any = None
    raw: str | None = None  # exactly as written on the card
    confidence: float = 0.0  # 0..1
    needs_check: bool = True
    note: str | None = None  # why it needs checking, in plain words


class DraftLine(BaseModel):
    kind: Literal["labour", "part", "fee"]
    description: str
    qty: float = 1
    unit_cents: int | None = None  # ex-GST; None = no price known yet
    part_id: int | None = None  # matched catalogue part, if any
    sku: str | None = None
    raw: str | None = None
    confidence: float = 0.0
    needs_check: bool = True
    note: str | None = None


class JobDraft(BaseModel):
    source: Literal["photo", "voice", "booking"] = "photo"
    title: str = ""
    customer_name: DraftField = Field(default_factory=DraftField)
    phone: DraftField = Field(default_factory=DraftField)  # E.164, e.g. +61412345678
    vehicle: DraftField = Field(default_factory=DraftField)  # {"make", "model", "year"}
    rego: DraftField = Field(default_factory=DraftField)  # upper-case, no spaces
    odometer_km: DraftField = Field(default_factory=DraftField)
    labour_hours: DraftField = Field(default_factory=DraftField)
    work_done: list[DraftField] = Field(default_factory=list)
    mechanic: DraftField = Field(default_factory=DraftField)
    notes: DraftField = Field(default_factory=DraftField)
    lines: list[DraftLine] = Field(default_factory=list)
    customer_id: int | None = None  # existing customer this card matched
    vehicle_id: int | None = None
    overall_confidence: float = 0.0
    readback: list[str] = Field(default_factory=list)  # what the app should ask aloud
    warnings: list[str] = Field(default_factory=list)
    photo_id: str | None = None
    models: dict[str, Any] = Field(default_factory=dict)
    readings: list[dict[str, Any]] = Field(default_factory=list)  # raw model output, for debugging
