"""Download and unpack Android/Java build tools only inside this project."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
TOOLS=ROOT/'.tools'
MAVEN='https://repo.maven.apache.org/maven2/'


def fetch(url,dest,sha256=None):
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and (not sha256 or hashlib.sha256(dest.read_bytes()).hexdigest()==sha256):
        return
    temporary=dest.with_suffix(dest.suffix+'.partial')
    urllib.request.urlretrieve(url,temporary)
    if sha256 and hashlib.sha256(temporary.read_bytes()).hexdigest()!=sha256:
        raise RuntimeError('Download checksum mismatch: '+dest.name)
    temporary.replace(dest)


def termux(item):
    name,info=item
    dest=TOOLS/'downloads'/Path(info['Filename']).name
    fetch('https://packages.termux.dev/apt/termux-main/'+info['Filename'],dest,info['SHA256'])
    subprocess.run(['dpkg-deb','-x',str(dest),str(TOOLS/'termux')],check=True)
    print('Ready:',name,flush=True)


def main():
    lock=json.loads((ROOT/'scripts/tool-lock.json').read_text())
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(termux,lock.items()))
    runtime={
      'chaquopy_java.jar':'com/chaquo/python/runtime/chaquopy_java/17.0.0/chaquopy_java-17.0.0.jar',
      'libchaquopy_java.so':'com/chaquo/python/runtime/libchaquopy_java/17.0.0/libchaquopy_java-17.0.0-3.14-arm64-v8a.so',
      'chaquopy.so':'com/chaquo/python/runtime/chaquopy/17.0.0/chaquopy-17.0.0-3.14-arm64-v8a.so',
      'bootstrap.imy':'com/chaquo/python/runtime/bootstrap/17.0.0/bootstrap-17.0.0-3.14.imy',
      'stdlib-common.imy':'com/chaquo/python/target/3.14.0-0/target-3.14.0-0-stdlib.zip',
      'native.zip':'com/chaquo/python/target/3.14.0-0/target-3.14.0-0-arm64-v8a.zip'}
    for name,url in runtime.items(): fetch(MAVEN+url,TOOLS/'chaquopy'/name)
    fetch('https://raw.githubusercontent.com/Sable/android-platforms/master/android-35/android.jar',TOOLS/'android.jar')
    fetch('https://storage.googleapis.com/r8-releases/raw/8.3.37/r8.jar',TOOLS/'r8.jar')
    fetch('https://raw.githubusercontent.com/chaquo/chaquopy/17.0.0/LICENSE.txt',TOOLS/'licenses/chaquopy.txt')
    fetch('https://raw.githubusercontent.com/python/cpython/v3.14.0/LICENSE',TOOLS/'licenses/python.txt')
    print('Build tools are ready.',flush=True)

if __name__=='__main__': main()
