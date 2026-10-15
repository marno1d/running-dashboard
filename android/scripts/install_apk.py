"""Hand the APK to Downloads without enabling Termux external-app access."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import threading
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
APK = ROOT / 'build/run-dashboard.apk'
VERSION = ET.parse(ROOT / 'app/AndroidManifest.xml').getroot().get('{http://schemas.android.com/apk/res/android}versionName')
DOWNLOAD_NAME = f'run-dashboard-{VERSION}.apk'

class Download(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.path not in ('/run-dashboard.apk', '/' + DOWNLOAD_NAME):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/vnd.android.package-archive')
        self.send_header('Content-Disposition', f'attachment; filename="{DOWNLOAD_NAME}"')
        self.send_header('Content-Length', str(APK.stat().st_size))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        try:
            with APK.open('rb') as source:
                shutil.copyfileobj(source, self.wfile)
        except (BrokenPipeError, ConnectionResetError):
            pass

if __name__ == '__main__':
    if not APK.exists():
        raise SystemExit('Build the APK first.')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Download)
    server.daemon_threads = True
    url = f'http://127.0.0.1:{server.server_port}/{DOWNLOAD_NAME}'
    print('Download URL:', url, flush=True)
    print('Available on this phone for 15 minutes. Open the downloaded APK to install.', flush=True)
    timer = threading.Timer(900, server.shutdown)
    timer.daemon = True
    timer.start()
    subprocess.run(['termux-open', '--view', url], check=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        timer.cancel()
        server.server_close()
