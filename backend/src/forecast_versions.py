"""逐日预测版本管理。

同一场站可能有两份已发布预测覆盖同一个运营日。跨场分流只能取当天
“在用”的版本：主管在预测工作台逐日换版，已启用或结案的分流所在日
保持锁定。所有换版以 request_id 幂等，回执丢失时同号重试不会重复换版。
"""
from datetime import date

from fastapi import HTTPException

from .db import connect
from .workflow import audit

LOCK_REASON_LABELS = {
    'diversion_active': '当天分流已启用，版本锁定',
    'diversion_closed': '当天分流已结案，历史版本冻结',
}


def lock_reason_label(reason):
    return LOCK_REASON_LABELS.get(reason, reason)


def _forecast_map(conn, forecast_ids):
    if not forecast_ids:
        return {}
    rows = conn.execute('SELECT id, code, status, lot_id, horizon_start, horizon_days FROM forecast_plan WHERE id = ANY(%s)',
                        (list(forecast_ids),)).fetchall()
    return {row['id']: row for row in rows}


def _published_predictions(conn, lot_id):
    """同一场站所有已发布且按天可覆盖的预测。"""
    plans = conn.execute('''SELECT * FROM forecast_plan WHERE lot_id=%s AND status='published'
        ORDER BY horizon_start, id''', (lot_id,)).fetchall()
    return plans


def _covers(plan, day):
    start = plan['horizon_start']
    return start <= day <= date.fromordinal(start.toordinal() + plan['horizon_days'] - 1)


def turnover_of(forecast, day):
    for point in forecast['predictions'] or []:
        if point['date'] == day.isoformat():
            return point['turnover']
    return None


def version_days(lot_code=None):
    """返回每个场站-运营日当前在用的预测版本与锁定原因。

    没有显式换版记录的日期，默认沿用该场站当天最早发布的预测版本；
    主管逐日换版后，forecast_day_version 中的固定版本生效。
    """
    with connect() as conn:
        lot_filter = ()
        lot_sql = ''
        if lot_code:
            lot_sql = 'WHERE l.code=%s'
            lot_filter = (lot_code,)
        lots = conn.execute(f'SELECT id, code, name FROM parking_lot l {lot_sql} ORDER BY l.code', lot_filter).fetchall()
        pinned = conn.execute(f'''SELECT v.* FROM forecast_day_version v
            JOIN parking_lot l ON l.id=v.lot_id {lot_sql} ORDER BY v.service_day''', lot_filter).fetchall()
        result = []
        for lot in lots:
            plans = _published_predictions(conn, lot['id'])
            days = {}
            for plan in plans:
                for offset in range(plan['horizon_days']):
                    day = date.fromordinal(plan['horizon_start'].toordinal() + offset)
                    days.setdefault(day, []).append(plan)
            pinned_rows = [row for row in pinned if row['lot_id'] == lot['id']]
            plan_ids = {plan['id'] for plan in plans} | {row['forecast_id'] for row in pinned_rows}
            plan_map = _forecast_map(conn, plan_ids)
            for row in pinned_rows:
                plan = plan_map.get(row['forecast_id'])
                result.append(_day_row(lot, row['service_day'], plan, plans, row))
                days.pop(row['service_day'], None)
            for day in sorted(days):
                day_plans = days[day]
                # 未显式换版的日期沿用最早发布版本；新版只有在主管逐日换版后才生效。
                effective = min(day_plans, key=lambda plan: (plan['created_at'], plan['id']))
                result.append(_day_row(lot, day, effective, day_plans, None))
        result.sort(key=lambda item: (item['lot_code'], item['service_day']))
        return result


def _day_row(lot, day, effective_plan, candidates, pinned):
    alternatives = []
    for plan in candidates:
        if effective_plan and plan['id'] == effective_plan['id']:
            continue
        if _covers(plan, day):
            alternatives.append({'forecast_id': plan['id'], 'forecast_code': plan['code']})
    return {
        'lot_id': lot['id'],
        'lot_code': lot['code'],
        'lot_name': lot['name'],
        'service_day': day.isoformat(),
        'forecast_id': effective_plan['id'] if effective_plan else None,
        'forecast_code': effective_plan['code'] if effective_plan else None,
        'locked': bool(pinned and pinned['locked']),
        'lock_reason': pinned['lock_reason'] if pinned else None,
        'lock_reason_label': lock_reason_label(pinned['lock_reason']) if pinned and pinned['locked'] else None,
        'explicitly_switched': bool(pinned and pinned['switched_by']),
        'alternatives': alternatives,
    }


def effective_forecast_id(conn, lot_id, day):
    """取某场站某天在用的已发布预测 ID（调用方自行持有所需行锁）。"""
    pinned = conn.execute('SELECT forecast_id FROM forecast_day_version WHERE lot_id=%s AND service_day=%s',
                          (lot_id, day)).fetchone()
    if pinned:
        return pinned['forecast_id']
    plans = conn.execute('''SELECT id FROM forecast_plan WHERE lot_id=%s AND status='published'
        AND horizon_start <= %s AND horizon_start + horizon_days - 1 >= %s
        ORDER BY created_at ASC, id ASC''', (lot_id, day, day)).fetchall()
    if not plans:
        return None
    return plans[0]['id']


def lock_day_version(conn, lot_id, day, forecast_id, reason, actor):
    """分流启用/结案时把当天版本锁定在其引用的预测上。

    已锁定但指向其他预测版本时拒绝，保证“先换版则旧草稿不能启用”。
    """
    row = conn.execute('''INSERT INTO forecast_day_version (lot_id, service_day, forecast_id, locked, lock_reason, switched_by)
        VALUES (%s,%s,%s,true,%s,%s)
        ON CONFLICT (lot_id, service_day) DO UPDATE
        SET locked = true,
            lock_reason = EXCLUDED.lock_reason,
            updated_at = now()
        RETURNING *''', (lot_id, day, forecast_id, reason, actor)).fetchone()
    if row['forecast_id'] != forecast_id:
        raise HTTPException(409, '当天已换用其他预测版本，引用旧版本的分流草稿不能启用，请按当天在用版本重新安排分流')
    return row


def release_day_lock(conn, lot_id, day):
    """分流撤销后，若当天再无启用/结案分流，则解除锁定，允许继续换版。"""
    remaining = conn.execute('''SELECT 1 FROM parking_diversion d JOIN capacity_closure c ON c.id=d.closure_id
        WHERE c.lot_id=%s AND d.service_day=%s AND d.status IN ('active','closed') LIMIT 1''',
        (lot_id, day)).fetchone()
    if remaining:
        return
    conn.execute('''UPDATE forecast_day_version SET locked=false, lock_reason=NULL, updated_at=now()
        WHERE lot_id=%s AND service_day=%s AND locked''', (lot_id, day))


def switch_version(item, actor):
    """逐日换版。request_id 幂等：同号重试返回首次结果，绝不重复换版。

    并发同号请求先在 request_id 唯一索引上排队：首个事务持有 processing
    占位行，其余事务等其提交后读取最终结果重放，不会各自再做一次换版。
    """
    with connect() as conn:
        # 第一步：抢占 request_id。抢不到说明同号请求已在处理或处理完。
        claimed = conn.execute('''INSERT INTO forecast_version_switch
            (request_id, status, requested_by) VALUES (%s,'processing',%s)
            ON CONFLICT (request_id) DO NOTHING RETURNING id''',
                               (item.request_id, actor)).fetchone()
        if not claimed:
            previous = conn.execute('SELECT * FROM forecast_version_switch WHERE request_id=%s',
                                    (item.request_id,)).fetchone()
            if previous and previous['status'] == 'processing':
                # 若首个事务仍在进行，这里会阻塞到它提交；拿到锁后仍是 processing，
                # 说明原事务已异常退出（崩溃回收），本请求回收占位继续处理。
                conn.execute('SELECT id FROM forecast_version_switch WHERE request_id=%s FOR UPDATE',
                             (item.request_id,)).fetchone()
                previous = conn.execute('SELECT * FROM forecast_version_switch WHERE request_id=%s',
                                        (item.request_id,)).fetchone()
            if previous and previous['status'] != 'processing':
                return _replay(previous)

        lot = conn.execute('SELECT * FROM parking_lot WHERE code=%s FOR UPDATE', (item.lot_code,)).fetchone()
        if not lot:
            return _reject(conn, item, actor, None, None, '停车场不存在', missing=True)
        target = conn.execute('SELECT * FROM forecast_plan WHERE code=%s FOR UPDATE', (item.forecast_code,)).fetchone()
        if not target:
            return _reject(conn, item, actor, lot['id'], None, '预测方案不存在', missing=True)
        if target['lot_id'] != lot['id']:
            return _reject(conn, item, actor, lot['id'], target['id'], '预测与停车场不属于同一场站')
        if target['status'] != 'published':
            return _reject(conn, item, actor, lot['id'], target['id'], '只有已发布预测才能换为当天在用版本')
        if not _covers(target, item.service_day):
            return _reject(conn, item, actor, lot['id'], target['id'], '该预测未覆盖所选运营日')

        day_row = conn.execute('SELECT * FROM forecast_day_version WHERE lot_id=%s AND service_day=%s FOR UPDATE',
                               (lot['id'], item.service_day)).fetchone()
        if day_row and day_row['locked']:
            return _reject(conn, item, actor, lot['id'], target['id'],
                           lock_reason_label(day_row['lock_reason']))

        current_id = day_row['forecast_id'] if day_row else effective_forecast_id(conn, lot['id'], item.service_day)
        if current_id is None:
            return _reject(conn, item, actor, lot['id'], target['id'], '该场站当天没有可切换的已发布预测')
        if current_id == target['id']:
            return _reject(conn, item, actor, lot['id'], target['id'], '该预测已是当天在用版本，无需换版')

        conn.execute('''INSERT INTO forecast_day_version (lot_id, service_day, forecast_id, locked, lock_reason, switched_by)
            VALUES (%s,%s,%s,false,NULL,%s)
            ON CONFLICT (lot_id, service_day) DO UPDATE
            SET forecast_id=EXCLUDED.forecast_id, locked=false, lock_reason=NULL,
                switched_by=EXCLUDED.switched_by, updated_at=now()''',
                     (lot['id'], item.service_day, target['id'], actor))
        saved = conn.execute('''UPDATE forecast_version_switch
            SET lot_id=%s, service_day=%s, from_forecast_id=%s, to_forecast_id=%s, status='applied'
            WHERE request_id=%s RETURNING *''',
                             (lot['id'], item.service_day, current_id, target['id'], item.request_id)).fetchone()
        audit(conn, actor, 'forecast_version', saved['id'], 'switched',
              f"{lot['code']} {item.service_day} 换版至 {target['code']}（request {item.request_id}）")
        return _record_from_row(conn, saved, idempotent_replay=False)


def _record_from_row(conn, row, idempotent_replay):
    lot = conn.execute('SELECT code, name FROM parking_lot WHERE id=%s', (row['lot_id'],)).fetchone() if row['lot_id'] else None
    target = conn.execute('SELECT code FROM forecast_plan WHERE id=%s', (row['to_forecast_id'],)).fetchone() if row['to_forecast_id'] else None
    source = conn.execute('SELECT code FROM forecast_plan WHERE id=%s', (row['from_forecast_id'],)).fetchone() if row['from_forecast_id'] else None
    return {
        'request_id': row['request_id'],
        'lot_code': lot['code'] if lot else None,
        'lot_name': lot['name'] if lot else None,
        'service_day': row['service_day'].isoformat() if row['service_day'] else None,
        'from_forecast_code': source['code'] if source else None,
        'forecast_code': target['code'] if target else None,
        'status': row['status'],
        'reject_reason': row['reject_reason'],
        'idempotent_replay': idempotent_replay,
        'created_at': row['created_at'].isoformat(),
    }


def _reject(conn, item, actor, lot_id, target_id, reason, missing=False):
    """拒绝也要落库留痕并占用 request_id，保证重试不产生第二次换版。"""
    saved = conn.execute('''UPDATE forecast_version_switch
        SET lot_id=%s, service_day=%s, to_forecast_id=%s, status='rejected', reject_reason=%s
        WHERE request_id=%s AND status='processing' RETURNING *''',
                         (lot_id, item.service_day, target_id, reason, item.request_id)).fetchone()
    if saved:
        audit(conn, actor, 'forecast_version', saved['id'], 'switch_rejected',
              f"{item.lot_code} {item.service_day} -> {item.forecast_code}：{reason}（request {item.request_id}）")
    conn.commit()
    raise HTTPException(404 if missing else 409, reason)


def _replay(previous):
    with connect() as conn:
        record = _record_from_row(conn, previous, idempotent_replay=True)
    if previous['status'] == 'rejected':
        raise HTTPException(409, f"该换版请求已被拒绝（幂等重试）：{previous['reject_reason']}")
    return record
