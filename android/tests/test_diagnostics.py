"""Local diagnostic capability and report validation, using synthetic error text."""
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'common'),str(ROOT/'android/scripts'),str(ROOT/'android/app/src/main/python')]
from diagnostic_contract import validate_diagnostics
from receive_diagnostics import Receiver


class DiagnosticsTest(unittest.TestCase):
    payload=dict(schema=1,kind='diagnostics',report='Run Dashboard test\nException: java.lang.OutOfMemoryError\n  at dev.rundashboard.app.MainActivity.renderTargetPaces:100',android_api=35,max_heap_mb=256)
    def test_schema_rejects_unexpected_metadata_and_oversized_text(self):
        self.assertEqual(validate_diagnostics(self.payload),self.payload)
        for changes in (dict(tokens='secret'),dict(report='x'*65537),dict(android_api=True),dict(max_heap_mb=float('inf'))):
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_diagnostics(dict(self.payload,**changes))
    def test_local_receiver_validates_token_and_keeps_private_report_history(self):
        with tempfile.TemporaryDirectory() as folder:
            server=ThreadingHTTPServer(('127.0.0.1',0),Receiver);server.daemon_threads=True
            server.token='x'*32;server.received=False;server.destination=Path(folder)/'latest.json'
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            def request(method,path,body=None):
                connection=HTTPConnection('127.0.0.1',server.server_port,timeout=5)
                try:
                    connection.request(method,path,body);response=connection.getresponse();status=response.status;data=response.read();return status,data
                finally:connection.close()
            try:
                self.assertEqual(request('POST','/diagnostics/wrong',json.dumps(self.payload))[0],403)
                self.assertEqual(request('POST','/diagnostics/'+server.token,'{"tokens":"secret"}')[0],400)
                self.assertFalse(server.destination.exists())
                self.assertEqual(request('GET','/diagnostics/'+server.token)[0],200)
                for i in range(2):self.assertEqual(request('POST','/diagnostics/'+server.token,json.dumps(self.payload))[0],200)
                self.assertEqual(json.loads(server.destination.read_text()),self.payload)
                self.assertEqual(server.destination.stat().st_mode & 0o777,0o600)
                self.assertEqual(len(list((Path(folder)/'diagnostics').glob('*.json'))),2)
            finally:server.shutdown();thread.join();server.server_close()


if __name__=='__main__':unittest.main()
