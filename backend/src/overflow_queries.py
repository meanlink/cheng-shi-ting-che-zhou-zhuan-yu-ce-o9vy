from .db import connect
from .operations import fetch

WINDOWS = '''SELECT w.*, f.code AS forecast_code, origin.code AS source_code, origin.name AS source_name,
    target.code AS target_code, target.name AS target_name, w.admitted - w.released AS parked
    FROM overflow_window w JOIN forecast_plan f ON f.id=w.forecast_id
    JOIN parking_lot origin ON origin.id=f.lot_id JOIN parking_lot target ON target.id=w.target_lot_id'''


def window_record(conn, window_id):
    return fetch(conn, WINDOWS + ' WHERE w.id=%s', (window_id,), '溢流窗口不存在')


def lock_window(conn, window_id):
    return fetch(conn, 'SELECT * FROM overflow_window WHERE id=%s FOR UPDATE', (window_id,), '溢流窗口不存在')


def list_windows():
    with connect() as conn:
        return conn.execute(WINDOWS + """ ORDER BY CASE w.status
            WHEN 'open' THEN 0 WHEN 'paused' THEN 1 WHEN 'approved' THEN 2 WHEN 'proposed' THEN 3
            WHEN 'ended' THEN 4 WHEN 'reconciled' THEN 5 ELSE 6 END, w.starts_at DESC, w.id DESC""").fetchall()


def gate_history(window_id):
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        window = window_record(conn, window_id)
        batches = conn.execute('''SELECT * FROM overflow_gate_batch WHERE window_id=%s
            ORDER BY id DESC LIMIT 100''', (window_id,)).fetchall()
        return {'window': window, 'batches': batches}


def closeout_history(window_id):
    with connect() as conn:
        conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        window = window_record(conn, window_id)
        revisions = conn.execute('''SELECT * FROM overflow_closeout WHERE window_id=%s
            ORDER BY revision DESC''', (window_id,)).fetchall()
        return {'window': window, 'revisions': revisions}
