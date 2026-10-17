"""App-private, transactional run cache. No credentials or original FIT files."""
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

FIELDS = ('activityId', 'activityName', 'startTimeLocal', 'distance', 'duration',
          'averageSpeed', 'averageHR', 'maxHR', 'elapsedDuration', 'movingDuration',
          'updateDate', 'lastUpdated', 'lastUpdatedDate', 'activityType',
          'activityTrainingLoad', 'elevationGain', 'elevationLoss', 'averageTemperature',
          'startTimeGMT', '_station_match', 'splitSummaries', 'fastestSplit_5000')


class RunCache:
    def __init__(self, path=None):
        if path:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path) if path else ':memory:')
        old = self.db.execute("SELECT 1 FROM sqlite_master WHERE name='coverage'").fetchone()
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        self.db.execute('CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, day TEXT, body TEXT, fingerprint TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS coverage (start TEXT, end TEXT)')
        self.db.execute('CREATE TABLE IF NOT EXISTS details (id TEXT, kind TEXT, body TEXT, PRIMARY KEY(id,kind))')

        self.db.execute('CREATE TABLE IF NOT EXISTS daily (day TEXT, kind TEXT, body TEXT, PRIMARY KEY(day,kind))')
        if old and version < 2:
            self.db.execute('DELETE FROM coverage')
            self.db.execute("DELETE FROM details WHERE kind='laps'")
        self.db.execute('CREATE TABLE IF NOT EXISTS sync_meta (key TEXT PRIMARY KEY, body TEXT)')
        self.db.execute('PRAGMA user_version=2')
        self.db.commit()

    def meta(self,key):
        row=self.db.execute('SELECT body FROM sync_meta WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else None

    def save_meta(self,key,body):
        with self.db:self.db.execute('INSERT OR REPLACE INTO sync_meta VALUES(?,?)',(key,json.dumps(body)))

    def daily(self, start, end, kind):
        return {row[0]:json.loads(row[1]) for row in self.db.execute(
            'SELECT day,body FROM daily WHERE day>=? AND day<=? AND kind=?',(start,end,kind))}

    def save_day(self, day, kind, body):
        with self.db:
            self.db.execute('INSERT OR REPLACE INTO daily VALUES(?,?,?)',(day,kind,json.dumps(body)))

    def close(self):
        self.db.close()

    def __del__(self):
        try:self.close()
        except Exception:pass

    def all_details(self, kind):
        return {row[0]:json.loads(row[1]) for row in self.db.execute('SELECT id,body FROM details WHERE kind=?',(kind,))}

    def missing(self, start, end):
        cursor, last = date.fromisoformat(start), date.fromisoformat(end)
        gaps=[]
        for first, final in self.db.execute('SELECT start,end FROM coverage ORDER BY start'):
            first, final=date.fromisoformat(first),date.fromisoformat(final)
            if final<cursor:continue
            if first>last:break
            if first>cursor:gaps.append((cursor.isoformat(),(first-timedelta(days=1)).isoformat()))
            cursor=max(cursor,final+timedelta(days=1))
            if cursor>last:break
        if cursor<=last:gaps.append((cursor.isoformat(),last.isoformat()))
        return gaps

    def save_window(self, start, end, activities):
        """Commit a complete listing and invalidate details only for changed runs."""
        cleaned={}
        for row in activities:
            identity=str(row.get('activityId',''))
            stamp=row.get('startTimeLocal') or ''
            try:day=date.fromisoformat(stamp[:10]).isoformat()
            except (ValueError,TypeError):continue
            if not identity or not start<=day<=end:continue
            body={key:row[key] for key in FIELDS if key in row}
            if 'splitSummaries' in body:
                body['splitSummaries'] = [{key:split[key] for key in ('distance','duration','noOfSplits','splitType') if key in split}
                                          for split in body['splitSummaries'] if isinstance(split,dict)]
            body['activityId']=identity
            encoded=json.dumps(body,sort_keys=True,separators=(',',':'))
            cleaned[identity]=(day,encoded,hashlib.sha256(encoded.encode()).hexdigest())
        changed=[]
        with self.db:
            # Only remove a missing activity after a complete successful listing.
            previous=dict(self.db.execute('SELECT id,fingerprint FROM runs WHERE day>=? AND day<=?',(start,end)))
            for identity in previous.keys()-cleaned.keys():
                self.db.execute('DELETE FROM runs WHERE id=?',(identity,))
                self.db.execute('DELETE FROM details WHERE id=?',(identity,))
                changed.append(identity)
            for identity,(day,body,fingerprint) in cleaned.items():
                old=self.db.execute('SELECT fingerprint,body FROM runs WHERE id=?',(identity,)).fetchone()
                if old is not None and old[0]!=fingerprint:
                    before=json.loads(old[1]);after=json.loads(body)
                    inputs=('distance','duration','movingDuration','elapsedDuration','startTimeLocal','startTimeGMT','activityType','averageHR','maxHR','_station_match')
                    if any(before.get(key)!=after.get(key) for key in inputs):
                        self.db.execute('DELETE FROM details WHERE id=?',(identity,));changed.append(identity)
                self.db.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?)',(identity,day,body,fingerprint))
            windows=list(self.db.execute('SELECT start,end FROM coverage'))+[(start,end)]
            merged=[]
            for first,final in sorted(windows):
                if merged and date.fromisoformat(first)<=date.fromisoformat(merged[-1][1])+timedelta(days=1):
                    merged[-1]=(merged[-1][0],max(merged[-1][1],final))
                else:merged.append((first,final))
            self.db.execute('DELETE FROM coverage')
            self.db.executemany('INSERT INTO coverage VALUES(?,?)',merged)
        return changed

    def activities(self, start, end):
        return [json.loads(row[0]) for row in self.db.execute('SELECT body FROM runs WHERE day>=? AND day<=? ORDER BY day DESC',(start,end))]

    def detail(self, identity, kind):
        row=self.db.execute('SELECT body FROM details WHERE id=? AND kind=?',(identity,kind)).fetchone()
        return (True,json.loads(row[0])) if row else (False,None)

    def save_detail(self, identity, kind, body):
        with self.db:self.db.execute('INSERT OR REPLACE INTO details VALUES(?,?,?)',(identity,kind,json.dumps(body)))

    def clear(self):
        with self.db:
            for table in ('runs','coverage','details','daily','sync_meta'):self.db.execute('DELETE FROM '+table)
