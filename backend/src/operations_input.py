from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=500)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=80)]
PositiveId = Annotated[int, Field(gt=0)]
SpaceCount = Annotated[int, Field(gt=0, le=100000)]


class ClosureIn(BaseModel):
    reference: Reference
    lot_code: str
    starts_on: date
    ends_on: date
    blocked_spaces: SpaceCount
    reason: Note


class DiversionIn(BaseModel):
    closure_id: PositiveId
    forecast_code: str
    target_lot_code: str
    service_day: date
    reserved_spaces: SpaceCount
    dispatch_note: Note


class SettlementIn(BaseModel):
    diversion_id: PositiveId
    ledger_reference: Reference
    actual_diverted: int = Field(ge=0, le=1000000)
    analysis_note: Note


class ActionNote(BaseModel):
    note: Note
