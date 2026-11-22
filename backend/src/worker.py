import pathlib,time
from .db import redis_client
HEARTBEAT=pathlib.Path('/tmp/worker-heartbeat')
def main():
    client=redis_client()
    while True:
        HEARTBEAT.touch()
        try:
            event=client.rpop('parking:forecast-events')
            if event:
                pathlib.Path('/artifacts').mkdir(parents=True,exist_ok=True)
                with open('/artifacts/forecast-events.log','a',encoding='utf-8') as fh: fh.write(event+'\n')
        except Exception: pass
        time.sleep(3)
if __name__=='__main__': main()
