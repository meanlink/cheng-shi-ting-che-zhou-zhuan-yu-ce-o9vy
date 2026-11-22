from fastapi import HTTPException
import json
from .analytics import calendar_complete, rolling_backtest, seasonal_moving_average
from .db import connect, redis_client

def audit(conn, actor, entity_type, entity_id, action, detail):
    conn.execute('INSERT INTO audit_event(actor, entity_type, entity_id, action, detail) VALUES(%s,%s,%s,%s,%s)', (actor, entity_type, str(entity_id), action, detail))

def lots():
    with connect() as conn:
        return conn.execute('''SELECT l.*, COALESCE(o.entry_count,0) AS latest_entries, COALESCE(o.exit_count,0) AS latest_exits, o.observed_at AS latest_observed_at
        FROM parking_lot l LEFT JOIN LATERAL (SELECT entry_count, exit_count, observed_at FROM interval_observation WHERE lot_id=l.id ORDER BY observed_at DESC LIMIT 1) o ON TRUE ORDER BY l.code''').fetchall()

def observations(lot_code=None, limit=80):
    with connect() as conn:
        query = 'SELECT o.*, l.code AS lot_code, l.name AS lot_name FROM interval_observation o JOIN parking_lot l ON l.id=o.lot_id'; args=[]
        if lot_code: query += ' WHERE l.code=%s'; args.append(lot_code)
        query += ' ORDER BY o.observed_at DESC LIMIT %s'; args.append(limit)
        return conn.execute(query, args).fetchall()

def add_observation(item, actor):
    with connect() as conn:
        lot=conn.execute('SELECT * FROM parking_lot WHERE code=%s FOR UPDATE',(item.lot_code,)).fetchone()
        if not lot: raise HTTPException(404,'停车场不存在')
        if item.occupancy > lot['capacity']: raise HTTPException(422,f'占用数 {item.occupancy} 超过当前容量 {lot["capacity"]}')
        try:
            row=conn.execute('''INSERT INTO interval_observation(lot_id,observed_at,entry_count,exit_count,occupancy,source_file,source_row,entered_by)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id''',(lot['id'],item.observed_at,item.entry_count,item.exit_count,item.occupancy,item.source_file,item.source_row,actor)).fetchone()
        except Exception as exc:
            if 'duplicate key' in str(exc).lower(): raise HTTPException(409,'相同来源文件和行号已经录入')
            raise
        conn.execute('UPDATE parking_lot SET current_occupancy=%s,updated_at=now() WHERE id=%s',(item.occupancy,lot['id']))
        audit(conn,actor,'observation',row['id'],'recorded',f'{item.lot_code} {item.observed_at.isoformat()}')
        return row

def forecast_list():
    with connect() as conn:
        return conn.execute('SELECT f.*, l.code AS lot_code, l.name AS lot_name FROM forecast_plan f JOIN parking_lot l ON l.id=f.lot_id ORDER BY f.horizon_start DESC,f.id DESC').fetchall()

def forecast_detail(code):
    with connect() as conn: row=conn.execute('SELECT f.*, l.code AS lot_code, l.name AS lot_name, l.capacity AS current_capacity FROM forecast_plan f JOIN parking_lot l ON l.id=f.lot_id WHERE f.code=%s',(code,)).fetchone()
    if not row: raise HTTPException(404,'预测方案不存在')
    return row

def create_forecast(item,actor):
    with connect() as conn:
        lot=conn.execute('SELECT * FROM parking_lot WHERE code=%s',(item.lot_code,)).fetchone()
        if not lot: raise HTTPException(404,'停车场不存在')
        code=f'PF-{item.horizon_start.strftime("%Y%m%d")}-{item.lot_code.split("-")[-1]}'
        if conn.execute('SELECT code FROM forecast_plan WHERE code=%s',(code,)).fetchone():
            # 同场同起始日的第二版预测，保留首版编码并追加版次后缀。
            suffix=2
            while conn.execute('SELECT code FROM forecast_plan WHERE code=%s',(f'{code}-V{suffix}',)).fetchone():
                suffix+=1
            code=f'{code}-V{suffix}'
        row=conn.execute('INSERT INTO forecast_plan(code,lot_id,horizon_start,horizon_days,capacity_snapshot,created_by) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(code,lot['id'],item.horizon_start,item.horizon_days,lot['capacity'],actor)).fetchone()
        audit(conn,actor,'forecast',row['id'],'created',f'{code} capacity={lot["capacity"]}')
    return forecast_detail(code)

def run_forecast(code,actor):
    with connect() as conn:
        plan=conn.execute('SELECT f.*, l.code AS lot_code FROM forecast_plan f JOIN parking_lot l ON l.id=f.lot_id WHERE f.code=%s FOR UPDATE',(code,)).fetchone()
        if not plan: raise HTTPException(404,'预测方案不存在')
        rows=conn.execute('SELECT observed_at,entry_count,exit_count FROM interval_observation WHERE lot_id=%s ORDER BY observed_at',(plan['lot_id'],)).fetchall()
        complete=calendar_complete(rows,plan['horizon_start'])
        try: predictions=seasonal_moving_average(rows,plan['horizon_start'],plan['horizon_days']); mae,mape=rolling_backtest(rows)
        except ValueError as exc:
            conn.execute('UPDATE forecast_plan SET status=%s,calendar_complete=%s,updated_at=now() WHERE id=%s',('blocked',complete,plan['id']))
            audit(conn,actor,'forecast',plan['id'],'blocked',str(exc)); raise HTTPException(422,str(exc))
        status='pending_review' if complete else 'blocked'
        conn.execute('UPDATE forecast_plan SET status=%s,calendar_complete=%s,predictions=%s,mae=%s,mape=%s,model_version=%s,updated_at=now() WHERE id=%s',(status,complete,json.dumps(predictions),mae,mape,'seasonal-moving-average-v1',plan['id']))
        redis_client().lpush('parking:forecast-events',json.dumps({'code':code,'action':'backtested'}))
        audit(conn,actor,'forecast',plan['id'],'backtested' if complete else 'blocked',f'MAE={mae}; MAPE={mape}; calendar_complete={complete}')
    return forecast_detail(code)

def confirm_capacity(code,actor):
    with connect() as conn:
        plan=conn.execute('SELECT f.*,l.capacity AS current_capacity FROM forecast_plan f JOIN parking_lot l ON l.id=f.lot_id WHERE f.code=%s FOR UPDATE',(code,)).fetchone()
        if not plan: raise HTTPException(404,'预测方案不存在')
        if plan['status'] not in {'pending_review','blocked','backtested'}: raise HTTPException(409,'当前状态不能确认容量快照')
        conn.execute('UPDATE forecast_plan SET capacity_change_confirmed=true,capacity_snapshot=%s,updated_at=now() WHERE id=%s',(plan['current_capacity'],plan['id']))
        audit(conn,actor,'forecast',plan['id'],'capacity_confirmed',f'capacity={plan["current_capacity"]}')
    return forecast_detail(code)

def publish_forecast(code,actor,note):
    with connect() as conn:
        plan=conn.execute('SELECT * FROM forecast_plan WHERE code=%s FOR UPDATE',(code,)).fetchone()
        if not plan: raise HTTPException(404,'预测方案不存在')
        if plan['status']!='pending_review': raise HTTPException(409,'预测尚未通过回测，不能发布')
        if not plan['calendar_complete']: raise HTTPException(422,'缺少完整日历，禁止发布预测')
        if not plan['capacity_change_confirmed']: raise HTTPException(422,'车位容量变更未确认，禁止发布预测')
        conn.execute('UPDATE forecast_plan SET status=%s,reviewed_by=%s,review_note=%s,updated_at=now() WHERE id=%s',('published',actor,note,plan['id']))
        audit(conn,actor,'forecast',plan['id'],'published',note)
    return forecast_detail(code)

def reject_forecast(code,actor,note):
    with connect() as conn:
        plan=conn.execute('SELECT * FROM forecast_plan WHERE code=%s FOR UPDATE',(code,)).fetchone()
        if not plan: raise HTTPException(404,'预测方案不存在')
        if plan['status'] not in {'pending_review','blocked','backtested'}: raise HTTPException(409,'当前状态不能驳回')
        conn.execute('UPDATE forecast_plan SET status=%s,reviewed_by=%s,review_note=%s,updated_at=now() WHERE id=%s',('rejected',actor,note,plan['id']))
        audit(conn,actor,'forecast',plan['id'],'rejected',note)
    return forecast_detail(code)

def alerts():
    with connect() as conn:
        return conn.execute('SELECT a.*, f.code AS forecast_code, l.code AS lot_code, l.name AS lot_name FROM dispatch_alert a JOIN forecast_plan f ON f.id=a.forecast_id JOIN parking_lot l ON l.id=a.lot_id ORDER BY a.alert_time DESC,a.id DESC').fetchall()

def create_alert(item,actor):
    with connect() as conn:
        forecast=conn.execute('SELECT f.*,l.id AS lot_id FROM forecast_plan f JOIN parking_lot l ON l.id=f.lot_id WHERE f.code=%s',(item.forecast_code,)).fetchone()
        if not forecast: raise HTTPException(404,'预测方案不存在')
        if forecast['status']!='published': raise HTTPException(422,'只有已发布预测才能创建现场提醒')
        row=conn.execute('INSERT INTO dispatch_alert(forecast_id,lot_id,alert_time,zone,message,severity,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id',(forecast['id'],forecast['lot_id'],item.alert_time,item.zone,item.message,item.severity,actor)).fetchone()
        audit(conn,actor,'dispatch_alert',row['id'],'created',item.message)
    return next(a for a in alerts() if a['id']==row['id'])

def send_alert(alert_id,actor):
    with connect() as conn:
        row=conn.execute('SELECT * FROM dispatch_alert WHERE id=%s FOR UPDATE',(alert_id,)).fetchone()
        if not row: raise HTTPException(404,'提醒不存在')
        if row['status']!='draft': raise HTTPException(409,'只有草稿提醒可以发送')
        conn.execute('UPDATE dispatch_alert SET status=%s,sent_by=%s WHERE id=%s',('sent',actor,alert_id)); audit(conn,actor,'dispatch_alert',alert_id,'sent',row['message'])
    return next(a for a in alerts() if a['id']==alert_id)

def acknowledge_alert(alert_id,actor):
    with connect() as conn:
        row=conn.execute('SELECT * FROM dispatch_alert WHERE id=%s FOR UPDATE',(alert_id,)).fetchone()
        if not row: raise HTTPException(404,'提醒不存在')
        if row['status']!='sent': raise HTTPException(409,'只有已发送提醒可以确认')
        conn.execute('UPDATE dispatch_alert SET status=%s,acknowledged_by=%s WHERE id=%s',('acknowledged',actor,alert_id)); audit(conn,actor,'dispatch_alert',alert_id,'acknowledged',row['message'])
    return next(a for a in alerts() if a['id']==alert_id)

def audit_list():
    with connect() as conn: return conn.execute('SELECT * FROM audit_event ORDER BY occurred_at DESC LIMIT 60').fetchall()
