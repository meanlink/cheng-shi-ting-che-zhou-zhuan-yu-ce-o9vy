from fastapi import HTTPException

from .db import connect
from .overflow_queries import lock_window
from .overflow_rules import CloseoutStatus, WindowStatus, tally_variance
from .workflow import audit


def latest_revision(conn, window_id):
    return conn.execute('''SELECT * FROM overflow_closeout WHERE window_id=%s
        ORDER BY revision DESC LIMIT 1''', (window_id,)).fetchone()


def submit(window_id, item, actor):
    with connect() as conn:
        window = lock_window(conn, window_id)
        if window['status'] != WindowStatus.ENDED:
            raise HTTPException(409, '仅已结束且未结案的窗口可提交交班盘点')
        previous = latest_revision(conn, window_id)
        if previous and previous['status'] not in (CloseoutStatus.FLAGGED, CloseoutStatus.RETURNED):
            raise HTTPException(409, '当前盘点待主管复核，须退回后才能修订')
        admission_delta, release_delta, status = tally_variance(window, item)
        revision = previous['revision'] + 1 if previous else 1
        row = conn.execute('''INSERT INTO overflow_closeout (window_id,revision,ledger_reference,counted_admitted,
            counted_released,admission_delta,release_delta,note,status,submitted_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''', (window_id, revision, item.ledger_reference,
            item.counted_admitted, item.counted_released, admission_delta, release_delta, item.note, status, actor)).fetchone()
        audit(conn, actor, 'overflow_closeout', row['id'], status, f'{item.ledger_reference} · 第 {revision} 版')
        return row


def review(window_id, revision_id, accept, actor, note):
    with connect() as conn:
        window = lock_window(conn, window_id)
        current = latest_revision(conn, window_id)
        if window['status'] != WindowStatus.ENDED or not current or current['id'] != revision_id:
            raise HTTPException(409, '当前窗口或盘点版本已发生变化，请重新查看')
        if current['status'] != CloseoutStatus.READY:
            raise HTTPException(409, '仅与闸机流水一致的待复核盘点可审核，请先修正差异')
        status = CloseoutStatus.ACCEPTED if accept else CloseoutStatus.RETURNED
        row = conn.execute('''UPDATE overflow_closeout SET status=%s,reviewed_by=%s,review_note=%s
            WHERE id=%s RETURNING *''', (status.value, actor, note, revision_id)).fetchone()
        if accept:
            conn.execute("UPDATE overflow_window SET status='reconciled' WHERE id=%s", (window_id,))
            audit(conn, actor, 'overflow_window', window_id, 'reconciled', current['ledger_reference'])
        audit(conn, actor, 'overflow_closeout', revision_id, status.value, note)
        return row
