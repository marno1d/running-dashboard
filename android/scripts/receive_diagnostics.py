"""Serve the update and receive explicitly shared technical reports on localhost."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import secrets
import sys
import threading
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'common'))
from diagnostic_contract import validate_diagnostics
from install_apk import Download,DOWNLOAD_NAME
from receive_comparison import write_private


class Receiver(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,body,status=200):
        body=body.encode();self.send_response(status)
        for key,value in [('Content-Type','text/html; charset=utf-8'),('Content-Length',str(len(body))),('Cache-Control','no-store'),('Referrer-Policy','no-referrer')]:self.send_header(key,value)
        self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path in ('/run-dashboard.apk','/'+DOWNLOAD_NAME):return Download.do_GET(self)
        if not secrets.compare_digest(self.path,'/diagnostics/'+self.server.token):self.send_error(404);return
        intent=f'intent://diagnostics?port={self.server.server_port}&token={self.server.token}#Intent;scheme=rundashboard;package=dev.rundashboard.app;end'
        self.respond('''<!doctype html><meta name="viewport" content="width=device-width,initial-scale=1"><title>App error report</title>
<style>body{font:16px system-ui;max-width:700px;margin:32px auto;padding:0 18px;background:#f6f7f4;color:#1f2723}a{display:block;padding:16px;background:#287c71;color:white;border-radius:12px;margin:16px 0;text-decoration:none}</style>
<h1>App error report</h1><p>Install the update, then open the report and confirm sharing in the app. This screen opens independently of Garmin and saved charts.</p>
<p>Includes technical error locations, recent app operations and memory/process-exit information. Credentials, GPS coordinates, workout data and exception messages are excluded.</p>
<a href="/'''+DOWNLOAD_NAME+'">Install '+DOWNLOAD_NAME+'</a><a href="'+html.escape(intent,quote=True)+'">Open and share error report</a><p>'+('Report received. You can share again after reproducing a problem.' if self.server.received else 'Waiting for your explicit share.')+'</p>')
    def do_POST(self):
        if not secrets.compare_digest(self.path,'/diagnostics/'+self.server.token):self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=128*1024:raise ValueError('Invalid size')
            self.connection.settimeout(15)
            payload=validate_diagnostics(json.loads(self.rfile.read(length)))
            encoded=json.dumps(payload,indent=2)
            write_private(self.server.destination,encoded)
            write_private(self.server.destination.parent/'diagnostics'/f'report-{time.time_ns()}.json',encoded)
            self.server.received=True
        except Exception:self.send_error(400);return
        self.respond('Received');print('Received technical error report.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--minutes',type=int,default=60);args=parser.parse_args()
    os.umask(0o077);server=ThreadingHTTPServer(('127.0.0.1',0),Receiver);server.daemon_threads=True
    server.token=secrets.token_urlsafe(32);server.destination=ROOT/'.state/app-diagnostics.json';server.received=False
    print(f'http://127.0.0.1:{server.server_port}/diagnostics/{server.token}',flush=True)
    timer=threading.Timer(max(1,min(args.minutes,120))*60,server.shutdown);timer.daemon=True;timer.start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:timer.cancel();server.server_close()


if __name__=='__main__':main()
