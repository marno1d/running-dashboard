"""Build an ARM64 APK directly in Termux, without Gradle's x86 host tools.

Requires the dependencies in .venv and the tools downloaded by bootstrap.py.
Uses Chaquopy 17's public runtime artifacts and its standard APK asset layout.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / '.tools'
PREFIX = TOOLS / 'termux/data/data/com.termux/files/usr'
JAVA = PREFIX / 'lib/jvm/java-21-openjdk/bin'
BUILD = ROOT / 'build'
ABI = 'arm64-v8a'
ASSETS = BUILD / 'assets/chaquopy'
LIBS = BUILD / 'apk/lib' / ABI
PY_SITE = ROOT / '.venv/lib/python3.14/site-packages'
ENV = dict(os.environ, LD_LIBRARY_PATH=str(PREFIX / 'lib'), JAVA_HOME=str(JAVA.parent))
ENV['PATH'] = str(JAVA) + ':' + str(PREFIX / 'bin') + ':' + os.environ['PATH']


def run(*args):
    subprocess.run([str(arg) for arg in args], cwd=ROOT, env=ENV, check=True)


def zip_tree(dest, directory, predicate=lambda path: True):
    with zipfile.ZipFile(dest, 'w', zipfile.ZIP_DEFLATED) as out:
        for path in sorted(directory.rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and predicate(path):
                out.write(path, path.relative_to(directory))


def main():
    if not (JAVA / 'java').exists():
        raise SystemExit('Run python scripts/bootstrap.py first.')
    for folder in (BUILD / 'classes', BUILD / 'dex'):
        if folder.exists(): shutil.rmtree(folder)
    for folder in (ASSETS, LIBS, BUILD / 'classes', BUILD / 'dex'):
        folder.mkdir(parents=True, exist_ok=True)
    bootstrap = {'_bz2', '_ctypes', '_lzma', '_random', '_struct', 'binascii', 'math', 'mmap', 'zlib'}
    with zipfile.ZipFile(TOOLS / 'chaquopy/native.zip') as archive:
        with zipfile.ZipFile(ASSETS / f'stdlib-{ABI}.imy', 'w', zipfile.ZIP_DEFLATED) as stdlib:
            for name in archive.namelist():
                if name.endswith('/'):
                    continue
                filename = Path(name).name
                if name.startswith(f'jniLibs/{ABI}/'):
                    (LIBS / filename).write_bytes(archive.read(name))
                elif name.startswith(f'lib-dynload/{ABI}/'):
                    if filename.split('.')[0] in bootstrap:
                        target = ASSETS / 'bootstrap-native' / ABI / filename
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(archive.read(name))
                    else:
                        stdlib.writestr(filename, archive.read(name))
    for name in ('bootstrap.imy', 'stdlib-common.imy'):
        shutil.copyfile(TOOLS / 'chaquopy' / name, ASSETS / name)
    native_boot = ASSETS / 'bootstrap-native' / ABI / 'java'
    native_boot.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(TOOLS / 'chaquopy/chaquopy.so', native_boot / 'chaquopy.so')
    shutil.copyfile(TOOLS / 'chaquopy/libchaquopy_java.so', LIBS / 'libchaquopy_java.so')
    for name in ('libffi.so', 'libandroid-support.so'):
        shutil.copyfile(Path(os.environ['PREFIX']) / 'lib' / name, LIBS / name)
    for path in (PY_SITE / 'curl_cffi.libs').glob('*.so'):
        shutil.copyfile(path, LIBS / path.name)
    shutil.copyfile(PY_SITE / 'certifi/cacert.pem', ASSETS / 'cacert.pem')
    zip_tree(ASSETS / 'app.imy', ROOT / 'app/src/main/python')
    with zipfile.ZipFile(ASSETS / 'app.imy', 'a', zipfile.ZIP_DEFLATED) as app:
        for path in sorted((ROOT.parent / 'common').glob('*.py')):
            app.write(path, path.name)
        for name in ('build_dashboard.py','download_station_weather.py','download_activity_elevation.py'):
            app.write(ROOT.parent / 'web_app' / name, name)
    packages = {'garminconnect', 'requests', 'urllib3', 'certifi', 'charset_normalizer',
                'idna', 'ua_generator', 'curl_cffi', 'cffi', 'pycparser', 'fitdecode'}
    with zipfile.ZipFile(ASSETS / 'requirements-common.imy','w',zipfile.ZIP_DEFLATED) as common, \
         zipfile.ZipFile(ASSETS / f'requirements-{ABI}.imy','w',zipfile.ZIP_DEFLATED) as native:
        for path in sorted(PY_SITE.rglob('*')):
            relative = path.relative_to(PY_SITE)
            if not path.is_file() or '__pycache__' in relative.parts:
                continue
            if relative.parts[0] not in packages and not relative.parts[0].startswith('_cffi_backend.'):
                continue
            if path.suffix in ('.pyc', '.pyo'):
                continue
            target = native if path.suffix == '.so' else common
            if path.suffix == '.so':
                # Preserve file size and ELF offsets while removing build-host paths.
                raw = path.read_bytes()
                dynamic = subprocess.check_output(['readelf', '-d', str(path)], text=True)
                for entry in re.findall(r'(?:RPATH|RUNPATH).*?\[([^]]+)\]', dynamic):
                    if '/data/data/com.termux/' in entry:
                        old = entry.encode()
                        raw = raw.replace(old, b'$ORIGIN' + b'\0' * (len(old) - len(b'$ORIGIN')))
                target.writestr(str(relative), raw)
            else:
                target.write(path, str(relative))
        # Keep licenses alongside the code in the distributed app.
        for path in PY_SITE.glob('*.dist-info/**/*'):
            if path.is_file() and any(term in str(path).lower() for term in ('license', 'copying', 'notice')):
                common.write(path, str(path.relative_to(PY_SITE)))
    notices = BUILD / 'assets/notices'
    notices.mkdir(parents=True, exist_ok=True)
    for path in (TOOLS / 'licenses').glob('*'):
        shutil.copyfile(path, notices / path.name)
    for name in ('libffi', 'libandroid-support'):
        for path in (Path(os.environ['PREFIX']) / 'share/doc' / name).glob('*'):
            if path.is_file(): shutil.copyfile(path, notices / (name + '-' + path.name))
    shutil.copyfile(ROOT / 'THIRD_PARTY_NOTICES.md', notices / 'THIRD_PARTY_NOTICES.md')
    build_json = {'python_version':'3.14', 'extract_packages':[], 'assets':{}}
    for path in sorted(ASSETS.rglob('*')):
        if path.is_file() and path.name != 'build.json':
            build_json['assets'][str(path.relative_to(ASSETS))] = hashlib.sha1(path.read_bytes()).hexdigest()
    (ASSETS / 'build.json').write_text(json.dumps(build_json, indent=2))
    sources = list((ROOT / 'app/src/dev').rglob('*.java'))
    run(JAVA / 'javac','-source','8','-target','8','-cp',str(TOOLS / 'android.jar')+':'+str(TOOLS / 'chaquopy/chaquopy_java.jar'),'-d',BUILD / 'classes',*sources)
    run(JAVA / 'jar','cf',BUILD / 'app.jar','-C',BUILD / 'classes','.')
    run(JAVA / 'java','-cp',TOOLS / 'r8.jar','com.android.tools.r8.D8','--min-api','26','--lib',TOOLS / 'android.jar','--output',BUILD / 'dex',BUILD / 'app.jar',TOOLS / 'chaquopy/chaquopy_java.jar')
    run(PREFIX / 'bin/aapt','package','-f','-M',ROOT / 'app/AndroidManifest.xml','-I',TOOLS / 'android.jar','-S',ROOT / 'app/res','-A',BUILD / 'assets','-F',BUILD / 'unsigned.apk')
    with zipfile.ZipFile(BUILD / 'unsigned.apk','a') as apk:
        apk.write(BUILD / 'dex/classes.dex','classes.dex',compress_type=zipfile.ZIP_DEFLATED)
        for path in sorted(LIBS.glob('*.so')):
            apk.write(path,str(path.relative_to(BUILD / 'apk')),compress_type=zipfile.ZIP_DEFLATED)
    run(PREFIX / 'bin/zipalign','-f','4',BUILD / 'unsigned.apk',BUILD / 'aligned.apk')
    keystore = TOOLS / 'debug.jks'
    if not keystore.exists():
        run(JAVA / 'keytool','-genkeypair','-keystore',keystore,'-storepass','android','-keypass','android','-alias','androiddebugkey','-keyalg','RSA','-keysize','2048','-validity','10000','-dname','CN=Run Dashboard Debug')
    signer = PREFIX / 'share/java/apksigner.jar'
    run(JAVA / 'java','-jar',signer,'sign','--ks',keystore,'--ks-pass','pass:android','--key-pass','pass:android','--out',BUILD / 'run-dashboard.apk',BUILD / 'aligned.apk')
    run(JAVA / 'java','-jar',signer,'verify','--verbose',BUILD / 'run-dashboard.apk')
    print(f'Ready: {BUILD / "run-dashboard.apk"}',flush=True)

if __name__ == '__main__':
    main()
