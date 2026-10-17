"""Serve an APK and receive an explicit, cached comparison export on this phone."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import argparse
import html
import json
import os
from pathlib import Path
import secrets
import threading
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'common'))
from comparison_contract import validate_snapshot
from install_apk import Download,DOWNLOAD_NAME
from compare_dashboard import compare,markdown


def write_private(path,text):
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    temporary=path.with_suffix(path.suffix+'.tmp')
    descriptor=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    os.fchmod(descriptor,0o600)
    with os.fdopen(descriptor,'w') as output:output.write(text)
    temporary.replace(path)


class Receiver(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def respond(self,body,content_type='text/html; charset=utf-8',status=200):
        body=body.encode('utf-8')
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('Referrer-Policy','no-referrer');self.end_headers();self.wfile.write(body)
    def do_GET(self):
        if self.path in ('/run-dashboard.apk','/'+DOWNLOAD_NAME):
            return Download.do_GET(self)
        if not secrets.compare_digest(self.path,'/compare/'+self.server.token):
            self.send_error(404);return
        token=self.server.token;port=self.server.server_port
        terrain_intent='intent://terrain#Intent;scheme=rundashboard;package=dev.rundashboard.app;end'
        intent=f'intent://comparison?port={port}&token={token}#Intent;scheme=rundashboard;package=dev.rundashboard.app;end'
        report=self.server.state.get('report')
        detail='<p>Waiting for a saved-data export.</p>'
        if self.server.state.get('received'):detail='<p>Comparison is running. Reload this page in a moment.</p>'
        if self.server.state.get('error'):detail='<p>The comparison could not finish. The saved input remains available for inspection.</p>'
        if report:detail='<h2>Comparison report</h2><pre>'+html.escape(report)+'</pre>'
        self.respond('''<!doctype html><meta name="viewport" content="width=device-width, initial-scale=1"><title>Dashboard comparison</title>
<style>body{font:16px system-ui;max-width:760px;margin:32px auto;padding:0 18px;color:#1f2723;background:#f6f7f4}a{display:block;background:#287c71;color:white;padding:16px;border-radius:8px;margin:16px 0;text-decoration:none}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px}</style>
<h1>Terrain sync &amp; comparison</h1>
<p>Install the update, then open terrain sync. In the app tap <b>Download / resume terrain</b> and keep it open. Completed routes are saved. After the downloads finish, return here to share the saved results for comparison.</p>
<a href="/'''+DOWNLOAD_NAME+'">Install '+DOWNLOAD_NAME+'</a><a href="'+terrain_intent+'">Open terrain sync</a><a href="'+html.escape(intent,quote=True)+'">Share saved dashboard for comparison</a>'+detail)
    def do_POST(self):
        if not secrets.compare_digest(self.path,'/comparison/'+self.server.token):
            self.send_error(403);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16*1024*1024:raise ValueError('Invalid body size')
            payload=validate_snapshot(json.loads(self.rfile.read(length),parse_constant=lambda _:(_ for _ in ()).throw(ValueError('Non-finite number'))))
            with self.server.lock:
                if self.server.state.get('received'):
                    self.respond('Already received','text/plain',409);return
                write_private(ROOT/'.state/comparison-snapshot.json',json.dumps(payload,indent=2))
                self.server.state['received']=True
        except Exception:
            self.send_error(400);return
        self.respond('OK','text/plain')
        print('Received saved comparison:',len(payload['activities']),'activities',flush=True)
        threading.Thread(target=self.run_comparison,args=(payload,),daemon=True).start()
    def run_comparison(self,payload):
        try:
            report=compare(payload,matrix=True)
            rendered=markdown(report)
            write_private(ROOT/'.state/comparison-report.md',rendered)
            self.server.state['report']=rendered
            print('Comparison complete:',json.dumps(report['counts']),flush=True)
        except Exception:
            self.server.state['error']=True
            print('Comparison failed; saved input is retained for local debugging.',flush=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--minutes',type=int,default=30)
    args=parser.parse_args()
    os.umask(0o077)
    server=ThreadingHTTPServer(('127.0.0.1',0),Receiver)
    server.daemon_threads=True;server.token=secrets.token_urlsafe(32);server.state={};server.lock=threading.Lock()
    print(f'http://127.0.0.1:{server.server_port}/compare/{server.token}',flush=True)
    timer=threading.Timer(max(1,min(args.minutes,120))*60,server.shutdown);timer.daemon=True;timer.start()
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:timer.cancel();server.server_close()

if __name__=='__main__':main()
