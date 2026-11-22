import logging
from contextlib import asynccontextmanager
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from . import workflow, forecast_versions
from .auth import authenticate, current_user, require
from .contracts import AlertIn, ForecastIn, Login, ObservationIn, ReviewIn, Role
from .db import connect, migrate, redis_client
from .forecast_version_input import VersionSwitchIn
from .middlewares import quota_middleware, trace_middleware
from .operations_routes import router as operations_router
from .overflow_routes import router as overflow_router

logger=logging.getLogger('uvicorn.error')
analyst=require(Role.ANALYST,Role.SUPERVISOR); operator=require(Role.OPERATOR,Role.SUPERVISOR); supervisor=require(Role.SUPERVISOR)

@asynccontextmanager
async def lifespan(app):
    migrate()
    import os
    if os.getenv('SEED_DEMO','false').lower()=='true':
        from scripts.seed_demo import seed
        try: logger.info('Parking seed: %s',seed())
        except Exception: logger.exception('演示数据初始化失败')
    yield

app=FastAPI(title='城市停车周转预测',lifespan=lifespan)
app.include_router(operations_router)
app.include_router(overflow_router)
app.middleware('http')(quota_middleware); app.middleware('http')(trace_middleware)

@app.exception_handler(RequestValidationError)
async def invalid_input(request,exc):
    error=exc.errors()[0]; location='.'.join(str(part) for part in error['loc'][1:])
    return JSONResponse({'detail':f'请检查字段 {location}' if location else '请检查输入'},status_code=422)

@app.exception_handler(Exception)
async def all_errors(request,exc):
    if isinstance(exc,HTTPException): return JSONResponse({'detail':exc.detail},status_code=exc.status_code,headers=exc.headers)
    logger.exception('request failed'); return JSONResponse({'detail':'服务暂时不可用，请稍后重试'},status_code=500)

@app.get('/health')
def health():
    with connect() as conn: conn.execute('SELECT 1 FROM parking_lot LIMIT 1')
    redis_client().ping(); return {'status':'healthy'}
@app.post('/auth/login')
def login(item:Login): return authenticate(item.email,item.password)
@app.get('/auth/me')
def me(user=Depends(current_user)): return user
@app.get('/lots')
def get_lots(user=Depends(current_user)): return workflow.lots()
@app.get('/observations')
def get_observations(lot_code:str|None=None,user=Depends(current_user)): return workflow.observations(lot_code)
@app.post('/observations',status_code=201)
def post_observation(item:ObservationIn,user=Depends(analyst)): return workflow.add_observation(item,user['email'])
@app.get('/forecasts')
def get_forecasts(user=Depends(current_user)): return workflow.forecast_list()
@app.get('/forecasts/version-days')
def get_version_days(lot_code:str|None=None,user=Depends(current_user)): return forecast_versions.version_days(lot_code)
@app.post('/forecasts/versions/switch')
def switch_version(item:VersionSwitchIn,user=Depends(supervisor)): return forecast_versions.switch_version(item,user['email'])
@app.post('/forecasts',status_code=201)
def post_forecast(item:ForecastIn,user=Depends(analyst)): return workflow.create_forecast(item,user['email'])
@app.get('/forecasts/{code}')
def get_forecast(code:str,user=Depends(current_user)): return workflow.forecast_detail(code)
@app.post('/forecasts/{code}/run')
def run_forecast(code:str,user=Depends(analyst)): return workflow.run_forecast(code,user['email'])
@app.post('/forecasts/{code}/confirm-capacity')
def confirm_capacity(code:str,user=Depends(operator)): return workflow.confirm_capacity(code,user['email'])
@app.post('/forecasts/{code}/publish')
def publish(code:str,item:ReviewIn,user=Depends(supervisor)): return workflow.publish_forecast(code,user['email'],item.note)
@app.post('/forecasts/{code}/reject')
def reject(code:str,item:ReviewIn,user=Depends(supervisor)): return workflow.reject_forecast(code,user['email'],item.note)
@app.get('/alerts')
def get_alerts(user=Depends(current_user)): return workflow.alerts()
@app.post('/alerts',status_code=201)
def post_alert(item:AlertIn,user=Depends(operator)): return workflow.create_alert(item,user['email'])
@app.post('/alerts/{alert_id}/send')
def send_alert(alert_id:int,user=Depends(operator)): return workflow.send_alert(alert_id,user['email'])
@app.post('/alerts/{alert_id}/ack')
def ack_alert(alert_id:int,user=Depends(supervisor)): return workflow.acknowledge_alert(alert_id,user['email'])
@app.get('/audit')
def get_audit(user=Depends(current_user)): return workflow.audit_list()
