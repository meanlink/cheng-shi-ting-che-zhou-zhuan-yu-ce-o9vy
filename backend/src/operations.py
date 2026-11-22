from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException

from .db import connect
from .overflow_capacity import legacy_closure_peak, legacy_commitments, peak_window_commitment
from .workflow import audit

CLOSURES = '''SELECT c.*, l.code AS lot_code, l.name AS lot_name, l.capacity,
    l.capacity - c.blocked_spaces AS effective_capacity
    FROM capacity_closure c JOIN parking_lot l ON l.id=c.lot_id'''
DIVERSION_JOINS = '''FROM parking_diversion d JOIN capacity_closure c ON c.id=d.closure_id
    JOIN parking_lot source ON source.id=c.lot_id
    JOIN parking_lot target ON target.id=d.target_lot_id JOIN forecast_plan f ON f.id=d.forecast_id'''
DIVERSIONS = f'''SELECT d.*, c.reference AS closure_reference, source.name AS source_name,
    target.name AS target_name, f.code AS forecast_code {DIVERSION_JOINS}'''
SETTLEMENTS = '''SELECT s.*, d.service_day, source.name AS source_name, target.name AS target_name,
    d.forecast_turnover, d.reserved_spaces,
    s.observed_turnover - d.forecast_turnover AS turnover_delta,
    round((s.observed_turnover - d.forecast_turnover) * 100 / nullif(d.forecast_turnover, 0), 1) AS turnover_delta_pct,
    s.actual_diverted - d.reserved_spaces AS diversion_delta
    FROM diversion_settlement s JOIN parking_diversion d ON d.id=s.diversion_id
    JOIN capacity_closure c ON c.id=d.closure_id JOIN parking_lot source ON source.id=c.lot_id
    JOIN parking_lot target ON target.id=d.target_lot_id'''


def utc_today():
    return datetime.now(timezone.utc).date()


def fetch(conn, sql, args, missing):
    row = conn.execute(sql, args).fetchone()
    if row is None:
        raise HTTPException(404, missing)
    return row


def closures():
    with connect() as conn:
        return conn.execute(CLOSURES + ' ORDER BY c.id DESC').fetchall()


def diversions():
    with connect() as conn:
        return conn.execute(DIVERSIONS + ' ORDER BY d.id DESC').fetchall()


def settlements():
    with connect() as conn:
        return conn.execute(SETTLEMENTS + ' ORDER BY s.id DESC').fetchall()


def propose_closure(item, actor):
    if item.starts_on < utc_today() or not 0 <= (item.ends_on - item.starts_on).days <= 29:
        raise HTTPException(422, '封控须从今日或之后开始，每单覆盖 1–30 个运营日')
    with connect() as conn:
        lot = fetch(conn, 'SELECT * FROM parking_lot WHERE code=%s', (item.lot_code,), '停车场不存在')
        if lot['status'] != 'active' or item.blocked_spaces >= lot['capacity']:
            raise HTTPException(422, '封控仅适用于运营场站，且至少保留一个车位')
        created = conn.execute('''INSERT INTO capacity_closure
            (reference,lot_id,starts_on,ends_on,blocked_spaces,reason,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (reference) DO NOTHING RETURNING id''',
            (item.reference, lot['id'], item.starts_on, item.ends_on, item.blocked_spaces, item.reason, actor)).fetchone()
        if created is None:
            raise HTTPException(409, '封控工单号已经存在')
        audit(conn, actor, 'capacity_closure', created['id'], 'proposed', item.reference)
        return conn.execute(CLOSURES + ' WHERE c.id=%s', (created['id'],)).fetchone()


def change_closure(closure_id, actor, role, action, note):
    with connect() as conn:
        # Serialize all decisions about this lot's dated space commitments.
        lot = fetch(conn, '''SELECT l.* FROM parking_lot l JOIN capacity_closure c ON c.lot_id=l.id
            WHERE c.id=%s FOR NO KEY UPDATE OF l''', (closure_id,), '封控工单不存在')
        row = fetch(conn, 'SELECT * FROM capacity_closure WHERE id=%s FOR UPDATE', (closure_id,), '封控工单不存在')
        if action == 'approve':
            if row['status'] != 'proposed' or row['starts_on'] < utc_today():
                raise HTTPException(409, '仅可批准尚未过期的待审工单')
            if lot['status'] != 'active' or row['blocked_spaces'] >= lot['capacity']:
                raise HTTPException(409, '场站无法按工单容量运行')
            window = (lot['id'], row['starts_on'], row['ends_on'])
            if conn.execute('''SELECT id FROM capacity_closure WHERE lot_id=%s AND status='approved'
                AND ends_on >= %s AND starts_on <= %s LIMIT 1''', window).fetchone():
                raise HTTPException(409, '该场站已有重叠的已批准封控')
            peak = legacy_closure_peak(conn, *window)
            if peak and peak > lot['capacity'] - row['blocked_spaces'] - lot['current_occupancy']:
                raise HTTPException(409, '封控会挤占已承诺的分流车位')
            conn.execute("UPDATE capacity_closure SET status='approved',approved_by=%s WHERE id=%s", (actor, closure_id))
            event = 'approved'
        else:
            if row['status'] == 'approved' and role != 'supervisor':
                raise HTTPException(403, '已批准封控须由主管取消')
            if row['status'] == 'cancelled':
                raise HTTPException(409, '工单已取消')
            if conn.execute("""SELECT id FROM parking_diversion WHERE closure_id=%s
                AND status <> 'cancelled' LIMIT 1""", (closure_id,)).fetchone():
                raise HTTPException(409, '工单已关联分流单，须先撤销未执行的分流')
            conn.execute("UPDATE capacity_closure SET status='cancelled',cancelled_by=%s WHERE id=%s", (actor, closure_id))
            event = 'cancelled'
        audit(conn, actor, 'capacity_closure', closure_id, event, note)
        return conn.execute(CLOSURES + ' WHERE c.id=%s', (closure_id,)).fetchone()


def propose_diversion(item, actor):
    if item.service_day < utc_today():
        raise HTTPException(422, '分流运营日不能早于今日')
    with connect() as conn:
        closure = fetch(conn, 'SELECT * FROM capacity_closure WHERE id=%s FOR UPDATE',
                        (item.closure_id,), '封控工单不存在')
        if closure['status'] != 'approved' or not closure['starts_on'] <= item.service_day <= closure['ends_on']:
            raise HTTPException(409, '分流运营日必须在已批准的封控窗口内')
        forecast = fetch(conn, 'SELECT * FROM forecast_plan WHERE code=%s', (item.forecast_code,), '预测方案不存在')
        point = next((point for point in forecast['predictions'] or []
                      if point['date'] == item.service_day.isoformat()), None)
        if forecast['lot_id'] != closure['lot_id'] or forecast['status'] != 'published' or point is None:
            raise HTTPException(422, '须使用同一来源场站已发布且覆盖该日的预测')
        target = fetch(conn, 'SELECT * FROM parking_lot WHERE code=%s', (item.target_lot_code,), '接收停车场不存在')
        if target['id'] == closure['lot_id'] or target['status'] != 'active' or item.reserved_spaces > target['capacity']:
            raise HTTPException(422, '接收场站须为另一运营场站，预留数不得超过其额定容量')
        created = conn.execute('''INSERT INTO parking_diversion
            (closure_id,forecast_id,target_lot_id,service_day,reserved_spaces,forecast_turnover,dispatch_note,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (closure_id,service_day) WHERE status <> 'cancelled'
            DO NOTHING RETURNING id''', (closure['id'], forecast['id'], target['id'], item.service_day,
            item.reserved_spaces, Decimal(str(point['turnover'])), item.dispatch_note, actor)).fetchone()
        if created is None:
            raise HTTPException(409, '此封控工单当天已有一张有效分流单')
        audit(conn, actor, 'parking_diversion', created['id'], 'proposed', item.dispatch_note)
        return conn.execute(DIVERSIONS + ' WHERE d.id=%s', (created['id'],)).fetchone()


def change_diversion(diversion_id, actor, action, note):
    with connect() as conn:
        row = fetch(conn, '''SELECT d.*, c.lot_id AS source_id FROM parking_diversion d
            JOIN capacity_closure c ON c.id=d.closure_id WHERE d.id=%s FOR UPDATE OF d''',
            (diversion_id,), '分流单不存在')
        if action == 'activate':
            if row['status'] != 'proposed' or row['service_day'] < utc_today():
                raise HTTPException(409, '仅可启用未过期的待执行分流单')
            lot = fetch(conn, 'SELECT * FROM parking_lot WHERE id=%s FOR NO KEY UPDATE',
                        (row['target_lot_id'],), '接收停车场不存在')
            blocked = conn.execute('''SELECT coalesce(sum(blocked_spaces),0) AS spaces
                FROM capacity_closure WHERE lot_id=%s AND status='approved' AND %s BETWEEN starts_on AND ends_on''',
                (lot['id'], row['service_day'])).fetchone()['spaces']
            reserved = legacy_commitments(conn, lot['id'], row['service_day'])
            reserved += peak_window_commitment(conn, lot['id'], row['service_day'], row['service_day'])
            headroom = max(0, lot['capacity'] - blocked - lot['current_occupancy'] - reserved)
            if lot['status'] != 'active' or row['reserved_spaces'] > headroom:
                raise HTTPException(409, f'接收场当前可承诺 {headroom} 位，无法启用此分流单')
            conn.execute("""UPDATE parking_diversion SET status='active',activated_by=%s,
                target_headroom_at_activation=%s WHERE id=%s""", (actor, headroom, diversion_id))
            event = 'activated'
        else:
            if row['status'] != 'proposed' and not (row['status'] == 'active' and row['service_day'] > utc_today()):
                raise HTTPException(409, '当天或已执行的分流需通过复盘结案')
            conn.execute("UPDATE parking_diversion SET status='cancelled',cancelled_by=%s WHERE id=%s", (actor, diversion_id))
            event = 'cancelled'
        audit(conn, actor, 'parking_diversion', diversion_id, event, note)
        return conn.execute(DIVERSIONS + ' WHERE d.id=%s', (diversion_id,)).fetchone()


def submit_settlement(item, actor):
    with connect() as conn:
        diversion = fetch(conn, '''SELECT d.*, c.lot_id FROM parking_diversion d
            JOIN capacity_closure c ON c.id=d.closure_id WHERE d.id=%s FOR UPDATE OF d''',
            (item.diversion_id,), '分流单不存在')
        if diversion['status'] != 'active' or diversion['service_day'] > utc_today():
            raise HTTPException(409, '仅可复盘已启用且运营日已到的分流单')
        actual = conn.execute('''SELECT count(*) AS samples, coalesce(sum(entry_count::bigint + exit_count),0) AS turnover
            FROM interval_observation WHERE lot_id=%s AND observed_at >= (%s::date::timestamp AT TIME ZONE 'UTC')
            AND observed_at <= now() AND observed_at < ((%s::date + 1)::timestamp AT TIME ZONE 'UTC')''',
            (diversion['lot_id'], diversion['service_day'], diversion['service_day'])).fetchone()
        if not actual['samples']:
            raise HTTPException(422, '来源场站该运营日缺少闸机观测，不能提交复盘')
        saved = conn.execute('''INSERT INTO diversion_settlement
            (diversion_id,ledger_reference,observation_count,observed_turnover,actual_diverted,analysis_note,submitted_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (diversion_id) DO UPDATE SET ledger_reference=EXCLUDED.ledger_reference,
                observation_count=EXCLUDED.observation_count,observed_turnover=EXCLUDED.observed_turnover,
                actual_diverted=EXCLUDED.actual_diverted,analysis_note=EXCLUDED.analysis_note,
                submitted_by=EXCLUDED.submitted_by,status='submitted',reviewed_by=NULL,review_note=NULL,
                revision=diversion_settlement.revision+1,updated_at=now()
            WHERE diversion_settlement.status='returned' RETURNING id,revision''',
            (item.diversion_id, item.ledger_reference, actual['samples'], actual['turnover'], item.actual_diverted,
             item.analysis_note, actor)).fetchone()
        if saved is None:
            raise HTTPException(409, '已有复盘待审，主管退回后才可重提')
        audit(conn, actor, 'diversion_settlement', saved['id'], 'submitted',
              f"第 {saved['revision']} 版 · {item.ledger_reference} · 闸机 {actual['turnover']} 次 · 实际分流 {item.actual_diverted} 辆 · {item.analysis_note}")
        return conn.execute(SETTLEMENTS + ' WHERE s.id=%s', (saved['id'],)).fetchone()


def review_settlement(settlement_id, actor, action, note):
    with connect() as conn:
        # Match submission's lock order (diversion, then settlement).
        diversion = fetch(conn, '''SELECT d.* FROM parking_diversion d JOIN diversion_settlement s ON s.diversion_id=d.id
            WHERE s.id=%s FOR UPDATE OF d''', (settlement_id,), '复盘单不存在')
        row = fetch(conn, 'SELECT * FROM diversion_settlement WHERE id=%s FOR UPDATE', (settlement_id,), '复盘单不存在')
        if row['status'] != 'submitted' or diversion['status'] != 'active':
            raise HTTPException(409, '仅可审核待审且尚未结案的复盘')
        status = 'accepted' if action == 'accept' else 'returned'
        conn.execute('UPDATE diversion_settlement SET status=%s,reviewed_by=%s,review_note=%s,updated_at=now() WHERE id=%s',
                     (status, actor, note, settlement_id))
        audit(conn, actor, 'diversion_settlement', settlement_id, status, note)
        if status == 'accepted':
            conn.execute("UPDATE parking_diversion SET status='closed' WHERE id=%s", (diversion['id'],))
            audit(conn, actor, 'parking_diversion', diversion['id'], 'closed', f'复盘 #{settlement_id} 通过')
        return conn.execute(SETTLEMENTS + ' WHERE s.id=%s', (settlement_id,)).fetchone()
