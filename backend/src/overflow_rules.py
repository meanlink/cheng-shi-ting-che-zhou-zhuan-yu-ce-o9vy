from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import HTTPException


class WindowStatus(str, Enum):
    PROPOSED = 'proposed'
    APPROVED = 'approved'
    OPEN = 'open'
    PAUSED = 'paused'
    ENDED = 'ended'
    RECONCILED = 'reconciled'
    CANCELLED = 'cancelled'


class CloseoutStatus(str, Enum):
    FLAGGED = 'flagged'
    READY = 'ready'
    RETURNED = 'returned'
    ACCEPTED = 'accepted'


def validate_window(starts_at, ends_at):
    start, end = (value.astimezone(timezone.utc) for value in (starts_at, ends_at))
    now = datetime.now(timezone.utc)
    if start.date() != end.date() or not timedelta(minutes=15) <= end - start <= timedelta(hours=8):
        raise HTTPException(422, '开放窗口须在同一 UTC 运营日内，时长 15 分钟至 8 小时')
    if start.date() < now.date() or end <= now or start > now + timedelta(days=14):
        raise HTTPException(422, '请选择尚未结束且未来 14 天内的开放窗口')
    return start.date()


def movement_balance(window, batch, now):
    if window['status'] not in (WindowStatus.OPEN, WindowStatus.PAUSED):
        raise HTTPException(409, '仅开放或暂停收车的窗口可登记闸机流水')
    if batch.admitted == batch.released == 0:
        raise HTTPException(422, '本批次至少登记一辆进场或离场车辆')
    if batch.admitted and (window['status'] == WindowStatus.PAUSED or now >= window['ends_at']):
        raise HTTPException(409, '入口已停止收车，仍可登记离场')
    parked = window['admitted'] - window['released']
    # A mixed batch is accounted for by clearing exits before admitting new cars.
    if batch.released > parked:
        raise HTTPException(409, f'场内仅有 {parked} 辆分流车辆，不能登记更多离场')
    available = window['bay_limit'] - (parked - batch.released)
    if batch.admitted > available:
        raise HTTPException(409, f'本批次最多可接收 {available} 辆，超额车辆须留在来源场站')
    return parked + batch.admitted - batch.released


def tally_variance(window, item):
    admission_delta = item.counted_admitted - window['admitted']
    release_delta = item.counted_released - window['released']
    status = CloseoutStatus.FLAGGED if admission_delta or release_delta else CloseoutStatus.READY
    return admission_delta, release_delta, status.value
