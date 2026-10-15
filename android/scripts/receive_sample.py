"""Receive an explicitly shared chart sample from the installed app.

Run this, install the update, then use the printed deep link or --open.
Only a random local capability URL accepts data; no Garmin tokens are received.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import os
import secrets
import subprocess
import threading

ROOT=Path(__file__).resolve().parents[1]
TOKEN=secrets.token_urlsafe(32)
ROW_FIELDS={'id','title','started','date','category','pace','distance','duration','laps','best_5k'}
EFFORT_FIELDS={'duration','distance','start_distance','end_distance','start_elapsed','end_elapsed','samples'}
LAP_FIELDS={'index','lap','pace','distance','duration','intensity'}

class Receiver(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_POST(self):
        if not secrets.compare_digest(self.path,'/sample/'+TOKEN):
            self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=1024*1024: raise ValueError()
            payload=json.loads(self.rfile.read(length))
            rows=payload['runs']
            if not isinstance(rows,list) or len(rows)>20: raise ValueError()
            clean=[]
            for row in rows:
                if not isinstance(row,dict) or set(row)-ROW_FIELDS: raise ValueError()
                if not all(isinstance(lap,dict) and not set(lap)-LAP_FIELDS for lap in row.get('laps',[])): raise ValueError()
                if 'best_5k' in row and (not isinstance(row['best_5k'],dict) or set(row['best_5k'])-EFFORT_FIELDS): raise ValueError()
                clean.append(row)
            state=ROOT/'.state';state.mkdir(mode=0o700,exist_ok=True)
            path=state/'training-sample.json'
            with path.open('w') as destination: json.dump({'runs':clean},destination,indent=2)
            path.chmod(0o600)
        except Exception:
            self.send_error(400);return
        self.send_response(200);self.send_header('Content-Length','2');self.end_headers();self.wfile.write(b'OK')
        print('Sample received:',len(clean),'runs at',path,flush=True)
        threading.Thread(target=self.server.shutdown,daemon=True).start()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--open',action='store_true');args=parser.parse_args()
    os.umask(0o077)
    server=ThreadingHTTPServer(('127.0.0.1',0),Receiver);server.daemon_threads=True
    url=f'rundashboard://sample?port={server.server_port}&token={TOKEN}'
    print('Open after installing Run Dashboard 0.4.0:',url,flush=True)
    timer=threading.Timer(900,server.shutdown);timer.daemon=True;timer.start()
    if args.open: subprocess.run(['termux-open','--view',url],check=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: timer.cancel();server.server_close()
