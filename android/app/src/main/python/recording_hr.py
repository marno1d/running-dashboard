"""Aggregate time at each recorded heart rate, without retaining GPS or FITs."""
from datetime import datetime
import io
import zipfile
import fitdecode


def heart_rate_histogram(raw):
    def read(data):
        histogram = {}
        previous = None
        with fitdecode.FitReader(io.BytesIO(data),check_crc=fitdecode.CrcCheck.RAISE,
                                 error_handling=fitdecode.ErrorHandling.IGNORE) as reader:
            for frame in reader:
                if not isinstance(frame,fitdecode.FitDataMessage) or frame.name!='record':
                    continue
                stamp = frame.get_value('timestamp',fallback=None)
                hr = frame.get_value('heart_rate',fallback=None)
                if not isinstance(stamp,datetime) or not isinstance(hr,(int,float)) or not 1 <= hr <= 255:
                    continue
                if previous:
                    delta = min(10,(stamp-previous[0]).total_seconds())
                    if delta>0:
                        key = str(int(previous[1]))
                        histogram[key] = histogram.get(key,0)+delta
                previous = stamp,hr
        return histogram
    if not isinstance(raw,bytes):
        raise ValueError('Missing original recording')
    if zipfile.is_zipfile(io.BytesIO(raw)):
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for item in archive.infolist():
                if item.filename.lower().endswith('.fit') and item.file_size <= 20*1024*1024:
                    return read(archive.read(item))
        return {}
    return read(raw)
