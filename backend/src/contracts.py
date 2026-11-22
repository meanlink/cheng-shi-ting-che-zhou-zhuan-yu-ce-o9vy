from datetime import date, datetime
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class Role(str, Enum):
    ANALYST = 'analyst'
    OPERATOR = 'operator'
    SUPERVISOR = 'supervisor'

class ForecastStatus(str, Enum):
    DRAFT = 'draft'
    BACKTESTED = 'backtested'
    BLOCKED = 'blocked'
    PENDING_REVIEW = 'pending_review'
    PUBLISHED = 'published'
    REJECTED = 'rejected'

class AlertStatus(str, Enum):
    DRAFT = 'draft'
    SENT = 'sent'
    ACKNOWLEDGED = 'acknowledged'

class Login(BaseModel):
    email: str
    password: str

class ObservationIn(BaseModel):
    lot_code: str
    observed_at: datetime
    entry_count: int = Field(ge=0)
    exit_count: int = Field(ge=0)
    occupancy: int = Field(ge=0)
    source_file: str = Field(min_length=3, max_length=120)
    source_row: str = Field(min_length=1, max_length=40)

class ForecastIn(BaseModel):
    lot_code: str
    horizon_start: date
    horizon_days: int = Field(ge=3, le=14)

class ReviewIn(BaseModel):
    note: str = Field(min_length=4, max_length=300)

class AlertIn(BaseModel):
    forecast_code: str
    alert_time: datetime
    zone: str = Field(min_length=1, max_length=40)
    message: str = Field(min_length=5, max_length=240)
    severity: str
    @field_validator('severity')
    @classmethod
    def valid_severity(cls, value):
        if value not in {'info','watch','critical'}:
            raise ValueError('severity 必须为 info、watch 或 critical')
        return value
