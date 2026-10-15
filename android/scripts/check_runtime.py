"""Smoke-test the APK's packaged Python and native networking dependencies.

Run after build_apk.py. Fetches Garmin's public sign-in page, without an account.
"""
from pathlib import Path
import os
import shutil
import subprocess
import zipfile

ROOT=Path(__file__).resolve().parents[1]
CHECK=ROOT/'.tools/runtime-check'
CHECK.mkdir(parents=True,exist_ok=True)
with zipfile.ZipFile(ROOT/'.tools/chaquopy/native.zip') as archive:
    archive.extractall(CHECK)
stdlib=CHECK/'stdlib'
stdlib.mkdir(exist_ok=True)
with zipfile.ZipFile(ROOT/'.tools/chaquopy/stdlib-common.imy') as archive:
    archive.extractall(stdlib)
packages=CHECK/'packages'
if packages.exists(): shutil.rmtree(packages)
packages.mkdir()
for name in ('requirements-common.imy','requirements-arm64-v8a.imy','app.imy'):
    with zipfile.ZipFile(ROOT/'build/assets/chaquopy'/name) as archive:
        archive.extractall(packages)
source=CHECK/'check.c'
source.write_text(r'''
#include <Python.h>
int main(int argc, char **argv) {
    Py_Initialize();
    int result = PyRun_SimpleString(
        "import garminconnect, curl_cffi, _cffi_backend, garmin_backend\n"
        "import _ssl, _csv, web_sources, dashboard_sources\n"
        "assert set(web_sources.stations.STATIONS) == {'KPVU', 'KSLC'}\n"
        "assert dashboard_sources.merge_weather({'temperature':70}, {})['temperatureF'] == 70\n"
        "print('Packaged shared weather, terrain, CSV and SSL: OK')\n"
        "from best_effort import best_from_original\n"
        "assert best_from_original(bytes.fromhex('0c10b3521e0000002e464954400000140002fd04860504860000e9a4350000000000e8eca43520a107007484'))['duration'] == 1000\n"
        "print('Packaged FIT decoder and fastest 5K: OK')\n"
        "from garminconnect.client import HAS_CFFI\n"
        "assert HAS_CFFI\n"
        "from curl_cffi import requests\n"
        "r = requests.get('https://sso.garmin.com/portal/sso/en-US/sign-in?clientId=GarminConnect', impersonate='chrome', timeout=30)\n"
        "print('Packaged CPython and Garmin networking imports: OK')\n"
        "print('Garmin public sign-in page HTTP:', r.status_code)\n"
        "assert r.status_code == 200\n");
    Py_Finalize();
    return result == 0 ? 0 : 1;
}
''')
libdir=ROOT/'build/apk/lib/arm64-v8a'
subprocess.run(['clang',str(source),'-I',str(CHECK/'include/python3.14'),'-L',str(libdir),'-lpython3.14','-o',str(CHECK/'check')],check=True)
env=dict(os.environ, PYTHONHOME=str(CHECK),
         PYTHONPATH=':'.join(map(str,[packages,stdlib,CHECK/'lib-dynload/arm64-v8a'])),
         LD_LIBRARY_PATH=str(libdir))
subprocess.run([str(CHECK/'check')],env=env,cwd=ROOT,check=True)
