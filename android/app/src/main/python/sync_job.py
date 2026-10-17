"""Cooperative sync cancellation, bounded retries, and persistent terrain pacing."""
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import time
import urllib.error
import urllib.request
from garminconnect.exceptions import GarminConnectConnectionError


class SyncPaused(Exception):
    pass


class TerrainDeferred(Exception):
    pass


class SyncJob:
    def __init__(self, progress=None):
        self.progress=progress

    def checkpoint(self):
        if self.progress is not None:
            check=getattr(self.progress,'isCancelled',None)
            if check is not None and check() is True:
                raise SyncPaused('Sync paused. Completed downloads are saved; resume when ready.')

    def __call__(self,label,completed=0,total=0):
        self.checkpoint()
        if self.progress is not None:self.progress.update(label,completed,total)

    def wait(self,seconds):
        remaining=max(0,seconds)
        while remaining>0:
            self.checkpoint()
            step=min(.25,remaining)
            time.sleep(step)
            remaining-=step
        self.checkpoint()

    def request(self,call,label):
        for attempt in range(3):
            self.checkpoint()
            try:return call()
            except (GarminConnectConnectionError,ConnectionError,TimeoutError,OSError) as error:
                if isinstance(error,urllib.error.HTTPError) and error.code<500 and error.code!=408:
                    raise
                if attempt==2:raise
                self(label+' · connection interrupted, retry '+str(attempt+1)+'/2')
                self.wait(1 if attempt==0 else 3)


class TerrainRequests:
    """Rate-limit every chunk, across activities and app restarts; never save GPS."""
    DAILY_BUDGET=900  # Leave headroom below the public service's shared-IP quota.
    def __init__(self,cache,job):
        self.cache,self.job=cache,job

    def state(self):
        return self.cache.meta('terrain_requests') or {}

    def ready(self):
        state=self.state();now=time.time()
        if state.get('retry_after',0)>now:
            raise TerrainDeferred('Terrain is paused by the elevation service. Resume after '+datetime.fromtimestamp(state['retry_after'],timezone.utc).strftime('%Y-%m-%d %H:%M UTC')+'.')
        if state.get('day')==datetime.now(timezone.utc).date().isoformat() and state.get('used',0)>=self.DAILY_BUDGET:
            raise TerrainDeferred('Today’s terrain request budget is used. Completed routes are saved; resume tomorrow.')

    def defer(self,seconds):
        state=self.state();state['retry_after']=time.time()+seconds
        self.cache.save_meta('terrain_requests',state)

    def __call__(self,request,timeout,context):
        for attempt in range(3):
            self.job.checkpoint();self.ready()
            state=self.state()
            self.job.wait(min(1.05,max(0,1.05-(time.time()-state.get('last_request',0)))))
            self.ready()
            now=time.time();day=datetime.now(timezone.utc).date().isoformat()
            used=state.get('used',0) if state.get('day')==day else 0
            self.cache.save_meta('terrain_requests',dict(day=day,used=used+1,last_request=now,retry_after=state.get('retry_after',0)))
            try:
                with urllib.request.urlopen(request,timeout=timeout,context=context) as response:
                    body=json.loads(response.read().decode('utf-8'))
                if not isinstance(body,dict):raise ValueError('Unexpected elevation response')
                if body.get('status')!='OK':
                    reason=str(body.get('error','')).lower()
                    if any(word in reason for word in ('limit','quota','too many','calls per day','maximum')):
                        self.defer(3600)
                        raise TerrainDeferred('The elevation service reached its request limit. Resume later; completed routes are saved.')
                    raise ValueError('Unexpected elevation response')
                if not isinstance(body.get('results'),list):raise ValueError('Unexpected elevation response')
                return body
            except urllib.error.HTTPError as error:
                error.close()
                if error.code==429:
                    retry=error.headers.get('Retry-After','') if error.headers else ''
                    try:delay=float(retry)
                    except ValueError:
                        try:delay=parsedate_to_datetime(retry).timestamp()-time.time()
                        except (ValueError,TypeError,OverflowError):delay=3600
                    self.defer(max(60,min(86400,delay)))
                    raise TerrainDeferred('The elevation service is limiting requests. Resume later; completed routes are saved.') from None
                if error.code<500 and error.code!=408:
                    self.defer(900)
                    raise TerrainDeferred('The elevation service is unavailable. Resume later; Garmin elevation remains available.') from None
            except (OSError,ValueError):
                pass
            if attempt<2:
                self.job('Terrain connection interrupted · retry '+str(attempt+1)+'/2')
                self.job.wait(1 if attempt==0 else 3)
        self.defer(300)
        raise TerrainDeferred('Terrain connection interrupted. Resume in a few minutes; completed routes are saved.')
