"""Fastest continuous 5,000 m from original FIT distance/timestamp records.

Boundaries are interpolated between recorded samples. Elapsed timestamps keep
pauses inside the segment; no distance or time is inferred from activity totals.
"""
from bisect import bisect_left, bisect_right
from datetime import datetime
import io
import math
import zipfile
import fitdecode


def fastest_5k(samples):
    """Minimize a rolling 5 km over a piecewise-linear distance/time track.

Check both start- and finish-aligned sample boundaries: checking only sample
starts misses minima when the finish lies exactly on a change of speed.
Repeated distances preserve arrival/departure times around stops.
"""
    chunks, chunk = [], []
    for distance, timestamp in samples:
        try:
            d, t = float(distance), float(timestamp)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(d) or not math.isfinite(t) or d < 0:
            continue
        if chunk and (d < chunk[-1][0] or t < chunk[-1][1]):
            chunks.append(chunk); chunk = []
        if chunk and t == chunk[-1][1]:
            if d == chunk[-1][0]:
                continue
            # Conflicting samples cannot imply instantaneous progress.
            chunks.append(chunk); chunk = []
        chunk.append((d, t))
    if chunk:
        chunks.append(chunk)
    best = None
    for track in chunks:
        if len(track) < 2 or track[-1][0] - track[0][0] < 5000:
            continue
        distances = [p[0] for p in track]
        times = [p[1] for p in track]
        lower, upper = distances[0], distances[-1] - 5000

        def at(distance, departure):
            index = (bisect_right(distances, distance) - 1 if departure
                     else bisect_left(distances, distance))
            if distances[index] == distance:
                return times[index]
            left = index if departure else index - 1
            right = left + 1
            weight = (distance - distances[left]) / (distances[right] - distances[left])
            return times[left] + weight * (times[right] - times[left])

        candidates = {lower, upper}
        candidates.update(d for d in distances if lower <= d <= upper)
        candidates.update(d - 5000 for d in distances if lower <= d - 5000 <= upper)
        for start in sorted(candidates):
            t0, t1 = at(start, True), at(start + 5000, False)
            duration = t1 - t0
            if duration > 0 and (best is None or duration < best['duration']):
                best = dict(duration=duration, distance=5000, start_distance=start,
                            end_distance=start + 5000, start_elapsed=t0 - times[0],
                            end_elapsed=t1 - times[0], samples=len(track),
                            method='fit_elapsed_interpolated')
    return best


def fit_samples(raw):
    """Keep only distance in metres and absolute seconds; discard GPS/HR."""
    result = []
    with fitdecode.FitReader(io.BytesIO(raw), check_crc=fitdecode.CrcCheck.RAISE,
                             error_handling=fitdecode.ErrorHandling.IGNORE) as reader:
        for frame in reader:
            if not isinstance(frame, fitdecode.FitDataMessage) or frame.name != 'record':
                continue
            distance = frame.get_value('distance', fallback=None)
            stamp = frame.get_value('timestamp', fallback=None)
            if distance is not None and isinstance(stamp, datetime):
                result.append((distance, stamp.timestamp()))
    return result


def best_from_original(raw):
    """Garmin ORIGINAL is normally a ZIP. FIT bytes are also accepted."""
    if not isinstance(raw, bytes):
        raise ValueError('Missing original recording')
    source = io.BytesIO(raw)
    if zipfile.is_zipfile(source):
        best = None
        with zipfile.ZipFile(source) as archive:
            for entry in archive.infolist():
                if not entry.filename.lower().endswith('.fit') or entry.file_size > 20 * 1024 * 1024:
                    continue
                candidate = fastest_5k(fit_samples(archive.read(entry)))
                if candidate and (best is None or candidate['duration'] < best['duration']):
                    best = candidate
        return best
    return fastest_5k(fit_samples(raw))
