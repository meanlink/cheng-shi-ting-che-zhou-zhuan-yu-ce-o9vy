from decimal import Decimal

from fastapi import HTTPException


def published_turnover(forecast, service_day):
    if forecast['status'] != 'published':
        raise HTTPException(409, '溢流窗口须关联已发布预测')
    for point in forecast['predictions'] or []:
        if point['date'] == service_day.isoformat():
            return Decimal(str(point['turnover']))
    raise HTTPException(422, '预测未覆盖此 UTC 运营日')


def legacy_commitments(conn, lot_id, day):
    return conn.execute('''SELECT coalesce(sum(reserved_spaces),0) AS spaces
        FROM parking_diversion WHERE target_lot_id=%s AND service_day=%s
        AND status IN ('active','closed')''', (lot_id, day)).fetchone()['spaces']


def peak_window_commitment(conn, lot_id, first_day, last_day):
    # The approval rule keeps windows on a target from overlapping. The largest
    # booking in the interval therefore determines the added all-day headroom.
    return conn.execute('''SELECT coalesce(max(bay_limit),0) AS spaces
        FROM overflow_window WHERE target_lot_id=%s AND service_day BETWEEN %s AND %s
        AND status IN ('approved','open','paused')''', (lot_id, first_day, last_day)).fetchone()['spaces']


def legacy_closure_peak(conn, lot_id, first_day, last_day):
    # Sum commitments on the same operating day before finding the worst day.
    return conn.execute('''WITH commitments AS (
        SELECT service_day, sum(reserved_spaces) AS spaces FROM parking_diversion
        WHERE target_lot_id=%s AND service_day BETWEEN %s AND %s AND status IN ('active','closed')
        GROUP BY service_day
        UNION ALL
        SELECT service_day, max(bay_limit) FROM overflow_window
        WHERE target_lot_id=%s AND service_day BETWEEN %s AND %s AND status IN ('approved','open','paused')
        GROUP BY service_day
    ) SELECT coalesce(max(daily.spaces),0) AS spaces FROM (
        SELECT sum(spaces) AS spaces FROM commitments GROUP BY service_day
    ) daily''', (lot_id, first_day, last_day, lot_id, first_day, last_day)).fetchone()['spaces']


def check_target_capacity(conn, lot, window, opening=False):
    if lot['status'] != 'active':
        raise HTTPException(409, '接收停车场当前无法运营')
    if conn.execute('''SELECT 1 FROM overflow_window WHERE target_lot_id=%s AND id<>%s
        AND status IN ('approved','open','paused') AND starts_at < %s AND ends_at > %s LIMIT 1''',
        (lot['id'], window['id'], window['ends_at'], window['starts_at'])).fetchone():
        raise HTTPException(409, '接收停车场已有时段重叠的溢流窗口')
    if opening and conn.execute('''SELECT 1 FROM overflow_window WHERE target_lot_id=%s AND id<>%s
        AND status IN ('open','paused') LIMIT 1''', (lot['id'], window['id'])).fetchone():
        raise HTTPException(409, '接收停车场仍有未结束的闸机窗口')
    day = window['service_day']
    blocked = conn.execute('''SELECT coalesce(sum(blocked_spaces),0) AS spaces FROM capacity_closure
        WHERE lot_id=%s AND status='approved' AND %s BETWEEN starts_on AND ends_on''', (lot['id'], day)).fetchone()['spaces']
    available = max(0, lot['capacity'] - lot['current_occupancy'] - blocked - legacy_commitments(conn, lot['id'], day))
    if window['bay_limit'] > available:
        raise HTTPException(409, f'扣除现场占用、封控与跨场分流后，接收场最多可承诺 {available} 位')
