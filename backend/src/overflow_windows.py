from datetime import datetime, timezone
from enum import Enum

from fastapi import HTTPException

from .db import connect
from .operations import fetch
from .overflow_capacity import check_target_capacity, published_turnover
from .overflow_queries import lock_window, window_record
from .overflow_rules import WindowStatus as Status, validate_window
from .workflow import audit


class WindowAction(str, Enum):
    APPROVE = 'approve'
    OPEN = 'open'
    PAUSE = 'pause'
    RESUME = 'resume'
    END = 'end'
    CANCEL = 'cancel'


TRANSITIONS = {
    WindowAction.APPROVE: ((Status.PROPOSED,), Status.APPROVED),
    WindowAction.OPEN: ((Status.APPROVED,), Status.OPEN),
    WindowAction.PAUSE: ((Status.OPEN,), Status.PAUSED),
    WindowAction.RESUME: ((Status.PAUSED,), Status.OPEN),
    WindowAction.END: ((Status.OPEN, Status.PAUSED), Status.ENDED),
    WindowAction.CANCEL: ((Status.PROPOSED, Status.APPROVED), Status.CANCELLED),
}


def propose(item, actor):
    service_day = validate_window(item.starts_at, item.ends_at)
    with connect() as conn:
        forecast = fetch(conn, 'SELECT * FROM forecast_plan WHERE code=%s',
                         (item.forecast_code,), '预测方案不存在')
        turnover = published_turnover(forecast, service_day)
        target = fetch(conn, 'SELECT * FROM parking_lot WHERE code=%s',
                       (item.target_lot_code,), '接收停车场不存在')
        if target['id'] == forecast['lot_id'] or target['status'] != 'active' or item.bay_limit > target['capacity']:
            raise HTTPException(422, '请选择另一运营停车场，且车位配额不得超过其额定容量')
        row = conn.execute('''INSERT INTO overflow_window
            (reference,forecast_id,target_lot_id,starts_at,ends_at,bay_limit,forecast_turnover,reason,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (reference) DO NOTHING RETURNING id''',
            (item.reference, forecast['id'], target['id'], item.starts_at, item.ends_at, item.bay_limit,
             turnover, item.reason, actor)).fetchone()
        if row is None:
            raise HTTPException(409, '溢流窗口编号已存在')
        audit(conn, actor, 'overflow_window', row['id'], 'proposed', item.reason)
        return window_record(conn, row['id'])


def change(window_id, action, actor, note):
    with connect() as conn:
        # Legacy closure and diversion decisions lock this same lot before checking commitments.
        lot = fetch(conn, '''SELECT l.* FROM parking_lot l JOIN overflow_window w ON l.id=w.target_lot_id
            WHERE w.id=%s FOR NO KEY UPDATE OF l''', (window_id,), '溢流窗口不存在')
        window = lock_window(conn, window_id)
        before, after = TRANSITIONS[action]
        if window['status'] not in before:
            raise HTTPException(409, '当前窗口状态不允许此操作')
        now = datetime.now(timezone.utc)
        if action in (WindowAction.OPEN, WindowAction.RESUME) and not window['starts_at'] <= now < window['ends_at']:
            raise HTTPException(409, '当前时间不在已安排的收车窗口内')
        if action == WindowAction.APPROVE and now >= window['ends_at']:
            raise HTTPException(409, '安排时段已结束，不能批准')
        if action in (WindowAction.APPROVE, WindowAction.OPEN, WindowAction.RESUME):
            check_target_capacity(conn, lot, window, opening=action != WindowAction.APPROVE)
        if action == WindowAction.END and window['admitted'] != window['released']:
            raise HTTPException(409, '仍有分流车辆停放，全部离场后才能结束窗口')

        conn.execute('''UPDATE overflow_window SET status=%s,
            approved_by=coalesce(%s,approved_by), opened_at=coalesce(%s,opened_at),
            ended_at=coalesce(%s,ended_at), pause_reason=coalesce(%s,pause_reason) WHERE id=%s''',
            (after.value, actor if action == WindowAction.APPROVE else None,
             now if action == WindowAction.OPEN else None, now if action == WindowAction.END else None,
             note if action == WindowAction.PAUSE else None, window_id))
        audit(conn, actor, 'overflow_window', window_id, action.value, note)
        return window_record(conn, window_id)
