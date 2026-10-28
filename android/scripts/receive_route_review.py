"""Receive an explicitly shared route review over a one-use local capability URL."""
import argparse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import html
import json
import os
from pathlib import Path
import secrets
import threading
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'common'))
from route_review_contract import validate_review
from install_apk import Download,DOWNLOAD_NAME
from receive_comparison import write_private
from review_routes import report


class Receiver(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,body,content_type='text/html; charset=utf-8',status=200):
        encoded=body.encode('utf-8');self.send_response(status)
        for key,value in [('Content-Type',content_type),('Content-Length',str(len(encoded))),('Cache-Control','no-store'),('Referrer-Policy','no-referrer')]:self.send_header(key,value)
        self.end_headers();self.wfile.write(encoded)
    def do_GET(self):
        if self.path in ('/run-dashboard.apk','/'+DOWNLOAD_NAME):return Download.do_GET(self)
        if not secrets.compare_digest(self.path,'/routes/'+self.server.token):self.send_error(404);return
        intent=f'intent://route-review?port={self.server.server_port}&token={self.server.token}#Intent;scheme=rundashboard;package=dev.rundashboard.app;end'
        detail='<p>Waiting for your in-app export.</p>'
        if self.server.state.get('received'):detail='<p>Data received. Return to the chat so we can review it together.</p><pre>'+html.escape(self.server.state.get('report','Preparing the review…'))+'</pre>'
        share='' if self.server.state.get('received') else '<a href="'+html.escape(intent,quote=True)+'">Share sessions and routes</a>'
        self.respond('''<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><title>Share route review</title>
<style>body{font:16px system-ui;max-width:760px;margin:32px auto;padding:0 18px;color:#1f2723;background:#f6f7f4}a{display:block;background:#287c71;color:white;padding:16px;border-radius:12px;margin:16px 0;text-decoration:none}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:13px}</style>
<h1>Share sessions &amp; routes</h1><p>Install the update if needed. In the app, use Sync now to download the latest sessions and gear links. Then return here, tap Share sessions and routes, and confirm sharing in Run Dashboard.</p>
<p>Includes all saved session summaries, linked activity gear, route configurations, reference elevation profiles and relative route drawings. Sends directly to the local project on this phone. Garmin credentials and geographic GPS coordinates are excluded. No new Garmin downloads are started.</p>
<a href="/'''+DOWNLOAD_NAME+'">Install '+DOWNLOAD_NAME+'</a>'+share+detail)
    def do_POST(self):
        if not secrets.compare_digest(self.path,'/route-review/'+self.server.token):self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=32*1024*1024:raise ValueError('Invalid size')
            self.connection.settimeout(30)
            payload=validate_review(json.loads(self.rfile.read(length),parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite number'))))
            with self.server.lock:
                if self.server.state.get('received'):self.respond('Already received','text/plain',409);return
                write_private(self.server.destination,json.dumps(payload,indent=2))
                self.server.state['received']=True
        except Exception as error:
            # Technical type only: never log uploaded values, tokens or coordinates.
            print('Route-review upload rejected: '+type(error).__name__,flush=True)
            self.send_error(400);return
        self.respond('OK','text/plain')
        print('Received route review:',len(payload['activities']),'sessions,',len(payload['routes']),'routes',flush=True)
        try:
            rendered=report(payload);write_private(self.server.destination.with_name('route-review-report.md'),rendered)
            self.server.state['report']=rendered;print('Route elevation review ready for local inspection.',flush=True)
        except Exception:print('Data saved; automatic review unavailable. Inspect the local snapshot.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--minutes',type=int,default=60);args=parser.parse_args()
    os.umask(0o077)
    server=ThreadingHTTPServer(('127.0.0.1',0),Receiver);server.daemon_threads=True
    server.token=secrets.token_urlsafe(32);server.state={};server.lock=threading.Lock()
    server.destination=ROOT/'.state/route-review-snapshot.json'
    print(f'http://127.0.0.1:{server.server_port}/routes/{server.token}',flush=True)
    timer=threading.Timer(max(1,min(args.minutes,120))*60,server.shutdown);timer.daemon=True;timer.start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:timer.cancel();server.server_close()


if __name__=='__main__':main()
