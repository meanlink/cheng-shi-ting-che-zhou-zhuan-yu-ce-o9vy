import time
from uuid import uuid4
from fastapi import Request
from fastapi.responses import JSONResponse
from .db import redis_client

async def trace_middleware(request: Request, call_next):
    request.state.request_id = uuid4().hex
    started = time.perf_counter()
    response = await call_next(request)
    response.headers['X-Request-ID'] = request.state.request_id
    response.headers['Server-Timing'] = f'app;dur={(time.perf_counter()-started)*1000:.1f}'
    if request.url.path != '/health': response.headers['Cache-Control'] = 'no-store'
    return response

async def quota_middleware(request: Request, call_next):
    if request.url.path == '/health': return await call_next(request)
    try:
        client = redis_client(); key = f"parking:quota:{request.client.host if request.client else 'unknown'}"
        count = client.incr(key)
        if count == 1: client.expire(key, 60)
        if count > 180: return JSONResponse({'detail':'请求频率过高，请稍后再试'}, status_code=429)
    except Exception: pass
    return await call_next(request)
