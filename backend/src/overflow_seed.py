from datetime import datetime, time, timedelta, timezone
import json

from .analytics import seasonal_moving_average


def seed_overflow(conn, source_id, target_id):
    day = datetime.now(timezone.utc).date() + timedelta(days=1)
    observations = conn.execute('''SELECT observed_at,entry_count,exit_count FROM interval_observation
        WHERE lot_id=%s ORDER BY observed_at''', (source_id,)).fetchall()
    predictions = seasonal_moving_average(observations, day, 3)
    code = f'PF-OVERFLOW-{day:%Y%m%d}'
    conn.execute('''INSERT INTO forecast_plan (code,lot_id,horizon_start,horizon_days,capacity_snapshot,
        status,calendar_complete,capacity_change_confirmed,predictions,model_version,created_by,reviewed_by,review_note)
        SELECT %s,l.id,%s,3,l.capacity,'published',true,true,%s,'seasonal-moving-average-v1',
        'analyst@metro.demo','supervisor@metro.demo','早高峰备用场开放参考' FROM parking_lot l WHERE l.id=%s
        ON CONFLICT (code) DO NOTHING''', (code, day, json.dumps(predictions), source_id))
    start = datetime.combine(day, time(0, 30), timezone.utc)
    conn.execute('''INSERT INTO overflow_window (reference,forecast_id,target_lot_id,starts_at,ends_at,bay_limit,
        forecast_turnover,reason,created_by) SELECT %s,id,%s,%s,%s,24,%s,%s,'operator@metro.demo'
        FROM forecast_plan WHERE code=%s ON CONFLICT (reference) DO NOTHING''',
        (f'OF-AM-{day:%Y%m%d}', target_id, start, start + timedelta(hours=2), predictions[0]['turnover'],
         '枢纽工作日早高峰，江畔文体中心开放地下二层备用车位', code))
