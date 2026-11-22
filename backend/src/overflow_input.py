from typing import Annotated

from pydantic import AwareDatetime, BaseModel, Field, StringConstraints

Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=48)]
Note = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=240)]


class WindowIn(BaseModel):
    reference: Reference
    forecast_code: Reference
    target_lot_code: Reference
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    bay_limit: int = Field(gt=0, le=10000)
    reason: Note


class DecisionIn(BaseModel):
    note: Note


class GateBatchIn(BaseModel):
    receipt: Reference
    admitted: int = Field(ge=0, le=10000)
    released: int = Field(ge=0, le=10000)


class CloseoutIn(BaseModel):
    ledger_reference: Reference
    counted_admitted: int = Field(ge=0, le=1000000000)
    counted_released: int = Field(ge=0, le=1000000000)
    note: Note
