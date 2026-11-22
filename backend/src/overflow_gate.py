from datetime import datetime, timezone

from fastapi import HTTPException

from .db import connect
from .overflow_queries import lock_window
from .overflow_rules import movement_balance
from .workflow import audit


def record_batch(window_id, item, actor):
    with connect() as conn:
        window = lock_window(conn, window_id)
        previous = conn.execute('SELECT * FROM overflow_gate_batch WHERE window_id=%s AND receipt=%s',
                                (window_id, item.receipt)).fetchone()
        if previous:
            if (previous['admitted'], previous['released']) != (item.admitted, item.released):
                raise HTTPException(409, '该闸机单号已使用，进出数与原流水不一致')
            return previous

        parked = movement_balance(window, item, datetime.now(timezone.utc))
        row = conn.execute('''INSERT INTO overflow_gate_batch
            (window_id,receipt,admitted,released,parked_after,recorded_by) VALUES (%s,%s,%s,%s,%s,%s)
            RETURNING *''', (window_id, item.receipt, item.admitted, item.released, parked, actor)).fetchone()
        conn.execute('''UPDATE overflow_window SET admitted=admitted+%s,released=released+%s,
            peak_parked=greatest(peak_parked,%s) WHERE id=%s''', (item.admitted, item.released, parked, window_id))
        audit(conn, actor, 'overflow_gate_batch', row['id'], 'recorded',
              f'{item.receipt} · 进 {item.admitted} · 出 {item.released}')
        return row
