from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

RequestId = Annotated[str, StringConstraints(strip_whitespace=True, min_length=8, max_length=80)]
LotCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=40)]
ForecastCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=4, max_length=80)]


class VersionSwitchIn(BaseModel):
    # note 放宽到可空，避免回执丢失后的同号重试在参数校验层被拦截，破坏幂等语义。
    request_id: RequestId
    lot_code: LotCode
    service_day: date
    forecast_code: ForecastCode
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = Field(
        default='逐日换版：按主管复核切换当天在用预测')
