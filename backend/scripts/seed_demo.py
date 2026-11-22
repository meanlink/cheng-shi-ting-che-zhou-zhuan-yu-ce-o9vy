from datetime import datetime,date,time,timedelta,timezone
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.analytics import rolling_backtest,seasonal_moving_average
from src.auth import password_hash
from src.db import connect,migrate
from src.overflow_seed import seed_overflow
USERS=[('analyst@metro.demo','林岚','analyst'),('operator@metro.demo','周航','operator'),('supervisor@metro.demo','顾宁','supervisor')]
def seed():
    migrate()
    with connect() as conn:
        for email,name,role in USERS:
            conn.execute('INSERT INTO staff(email,display_name,password_hash,role) VALUES(%s,%s,%s,%s) ON CONFLICT(email) DO NOTHING',(email,name,password_hash('ParkingDemo26!'),role))
        lots=[('PARK-07','环城东路枢纽停车场','东城区',420,['A区','B区','C区'],214),('PARK-12','江畔文体中心停车楼','滨江区',260,['地下1层','地下2层'],126)]
        lot_ids={}
        for code,name,district,capacity,zones,occupancy in lots:
            row=conn.execute('INSERT INTO parking_lot(code,name,district,capacity,zones,current_occupancy) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(code) DO UPDATE SET name=EXCLUDED.name,district=EXCLUDED.district,capacity=EXCLUDED.capacity,zones=EXCLUDED.zones,current_occupancy=EXCLUDED.current_occupancy RETURNING id',(code,name,district,capacity,zones,occupancy)).fetchone(); lot_ids[code]=(row or conn.execute('SELECT id FROM parking_lot WHERE code=%s',(code,)).fetchone())['id']
        start=date(2026,11,1)
        for code,lot_id in lot_ids.items():
            for i in range(22):
                d=start+timedelta(days=i); morning=70+(i%7)*8+(18 if d.weekday()>=5 else 0); evening=82+((i+2)%7)*7+(24 if d.weekday()>=5 else 0)
                if code=='PARK-12': morning-=18; evening-=16
                observed_at=datetime.combine(d,time(22,0),tzinfo=timezone.utc)
                conn.execute('INSERT INTO interval_observation(lot_id,observed_at,entry_count,exit_count,occupancy,source_file,source_row,entered_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(lot_id,observed_at,source_file,source_row) DO NOTHING',(lot_id,observed_at,morning,evening,120+(i*5)%90,'停车闸机_2026-11.csv',f'{code}-{d.isoformat()}','analyst@metro.demo'))
        lot=conn.execute('SELECT * FROM parking_lot WHERE code=%s',('PARK-07',)).fetchone(); rows=conn.execute('SELECT observed_at,entry_count,exit_count FROM interval_observation WHERE lot_id=%s ORDER BY observed_at',(lot['id'],)).fetchall(); predictions=seasonal_moving_average(rows,date(2026,11,23),7); mae,mape=rolling_backtest(rows)
        conn.execute('''INSERT INTO forecast_plan(code,lot_id,horizon_start,horizon_days,capacity_snapshot,status,calendar_complete,capacity_change_confirmed,predictions,mae,mape,model_version,created_by,review_note)
        VALUES(%s,%s,%s,%s,%s,'pending_review',true,true,%s,%s,%s,'seasonal-moving-average-v1','analyst@metro.demo','等待主管审核：容量快照已由现场确认') ON CONFLICT(code) DO NOTHING''',('PF-20261123-07',lot['id'],date(2026,11,23),7,lot['capacity'],json.dumps(predictions),mae,mape))
        lot12=conn.execute('SELECT * FROM parking_lot WHERE code=%s',('PARK-12',)).fetchone()
        rows12=conn.execute('SELECT observed_at,entry_count,exit_count FROM interval_observation WHERE lot_id=%s ORDER BY observed_at',(lot12['id'],)).fetchall()
        predictions12=seasonal_moving_average(rows12,date(2026,11,23),7); mae12,mape12=rolling_backtest(rows12)
        conn.execute('''INSERT INTO forecast_plan(code,lot_id,horizon_start,horizon_days,capacity_snapshot,status,calendar_complete,capacity_change_confirmed,predictions,mae,mape,model_version,created_by,review_note)
        VALUES(%s,%s,%s,%s,%s,'pending_review',true,false,%s,%s,%s,'seasonal-moving-average-v1','analyst@metro.demo','容量变更尚未由现场确认') ON CONFLICT(code) DO NOTHING''',('PF-20261123-12',lot12['id'],date(2026,11,23),7,lot12['capacity'],json.dumps(predictions12),mae12,mape12))
        forecast=conn.execute('SELECT id FROM forecast_plan WHERE code=%s',('PF-20261123-07',)).fetchone()
        if not conn.execute('SELECT id FROM dispatch_alert WHERE forecast_id=%s AND zone=%s',(forecast['id'],'南入口')).fetchone():
            conn.execute('INSERT INTO dispatch_alert(forecast_id,lot_id,alert_time,zone,message,severity,status,created_by,sent_by) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)',(forecast['id'],lot['id'],datetime(2026,11,23,8,0,tzinfo=timezone.utc),'南入口','周一早高峰预计周转 238 次，07:45 开启分流','watch','sent','operator@metro.demo','operator@metro.demo'))
        operations_day = datetime.now(timezone.utc).date() + timedelta(days=1)
        conn.execute('''INSERT INTO capacity_closure(reference,lot_id,starts_on,ends_on,blocked_spaces,reason,created_by)
            VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (reference) DO NOTHING''',
            ('WL-DEMO-07',lot['id'],operations_day,operations_day,72,'B区车位划线和道闸联调','operator@metro.demo'))
        seed_overflow(conn, lot_ids['PARK-07'], lot_ids['PARK-12'])
        # 同一场站、同一预测窗口的第二版已发布预测，供预测工作台逐日换版演示。
        v2_code='PF-20261123-07-V2'
        if not conn.execute('SELECT 1 FROM forecast_plan WHERE code=%s',(v2_code,)).fetchone():
            v2_points=[{**point,'turnover':round(point['turnover']*1.08,2)} for point in predictions]
            conn.execute('''INSERT INTO forecast_plan(code,lot_id,horizon_start,horizon_days,capacity_snapshot,status,
                calendar_complete,capacity_change_confirmed,predictions,mae,mape,model_version,created_by,reviewed_by,review_note)
                VALUES(%s,%s,%s,%s,%s,'published',true,true,%s,%s,%s,'seasonal-moving-average-v2','analyst@metro.demo',
                'supervisor@metro.demo','复核新增观测后发布的第二版预测，可在预测工作台逐日换版')''',
                (v2_code,lot['id'],date(2026,11,23),7,lot['capacity'],json.dumps(v2_points),mae,mape))
        conn.commit(); return {table:conn.execute(f'SELECT count(*) AS total FROM {table}').fetchone()['total'] for table in ('staff','parking_lot','interval_observation','forecast_plan','dispatch_alert','capacity_closure','parking_diversion','diversion_settlement','overflow_window','overflow_gate_batch','overflow_closeout','forecast_day_version','forecast_version_switch')}
if __name__=='__main__': print(json.dumps(seed(),ensure_ascii=False,sort_keys=True))
