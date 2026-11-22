import hashlib
import os
from datetime import datetime, timedelta, timezone
import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from .db import connect
from .contracts import Role

bearer = HTTPBearer(auto_error=False)
def password_hash(value): return hashlib.sha256(value.encode()).hexdigest()
def authenticate(email, password):
    with connect() as conn:
        user = conn.execute('SELECT email, display_name, role, password_hash FROM staff WHERE email=%s', (email,)).fetchone()
    if not user or user['password_hash'] != password_hash(password): raise HTTPException(401, '邮箱或密码不正确')
    payload = {'sub': user['email'], 'role': user['role'], 'exp': datetime.now(timezone.utc) + timedelta(hours=10)}
    token = jwt.encode(payload, os.getenv('JWT_SECRET','parking-turnover-local-key-change-this'), algorithm='HS256')
    return {'access_token': token, 'token_type': 'bearer', 'user': {'email': user['email'], 'display_name': user['display_name'], 'role': user['role']}}

def current_user(credentials: HTTPAuthorizationCredentials = Depends(bearer)):
    if not credentials: raise HTTPException(401, '请先登录')
    try: payload = jwt.decode(credentials.credentials, os.getenv('JWT_SECRET','parking-turnover-local-key-change-this'), algorithms=['HS256'])
    except jwt.PyJWTError: raise HTTPException(401, '登录已过期，请重新登录')
    with connect() as conn: user = conn.execute('SELECT email, display_name, role FROM staff WHERE email=%s', (payload.get('sub'),)).fetchone()
    if not user: raise HTTPException(401, '用户不存在')
    return user

def require(*roles):
    allowed = {r.value if isinstance(r, Role) else r for r in roles}
    def dependency(user=Depends(current_user)):
        if user['role'] not in allowed: raise HTTPException(403, '当前岗位没有执行该操作的权限')
        return user
    return dependency
