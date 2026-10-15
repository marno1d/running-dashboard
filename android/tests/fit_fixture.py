"""Small synthetic FIT recordings: no personal data."""
import io
import struct
import zipfile
from fitdecode.utils import compute_crc


def recording(samples, zipped=True):
    # FIT global message 20 (record): timestamp (253), distance (5, scale 100).
    body=b'\x40\x00\x00'+struct.pack('<H',20)+b'\x02\xfd\x04\x86\x05\x04\x86'
    for distance,seconds in samples:
        body+=b'\x00'+struct.pack('<II',900000000+round(seconds),round(distance*100))
    header=struct.pack('<BBHI4s',12,16,21171,len(body),b'.FIT')
    data=header+body
    data+=struct.pack('<H',compute_crc(data))
    if not zipped:return data
    out=io.BytesIO()
    with zipfile.ZipFile(out,'w') as archive:archive.writestr('synthetic.fit',data)
    return out.getvalue()
