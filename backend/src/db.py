import os
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
import redis

def connect():
    return psycopg.connect(host=os.getenv('PGHOST','localhost'), port=os.getenv('PGPORT','5432'), dbname=os.getenv('PGDATABASE','parking'), user=os.getenv('PGUSER','parking'), password=os.getenv('PGPASSWORD','parking-local-db'), row_factory=dict_row)

def migrate():
    migrations = Path(__file__).resolve().parents[1] / 'migrations'
    with connect() as conn:
        for migration in sorted(migrations.glob('*.sql')):
            conn.execute(migration.read_text())

def redis_client():
    return redis.from_url(os.getenv('REDIS_URL','redis://localhost:6379/0'), decode_responses=True)
