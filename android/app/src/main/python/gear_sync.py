"""Read-only Garmin gear catalog and bulk activity links, cached independently of FITs."""
import hashlib
import time
import uuid

CATALOG = 'gear_catalog_v1'
LINKS = 'gear_activities_v1'
ACTIVITY_GEAR = 'gear_v1'
MAX_AGE = 6 * 3600
PAGE_SIZE = 100


def _identity(value):
    if isinstance(value, bool):raise ValueError('Invalid activity identity')
    value = str(value)
    if not value.isascii() or not value.isdigit() or int(value) <= 0:
        raise ValueError('Invalid activity identity')
    return str(int(value))


def _text(value):
    if not isinstance(value, (str, int)) or isinstance(value, bool):return ''
    return ''.join(c for c in str(value) if c.isprintable()).strip()[:200]


def clean_catalog(raw):
    if not isinstance(raw, list) or len(raw) > 1000:
        raise ValueError('Unexpected gear catalog')
    items = {}
    for row in raw:
        if not isinstance(row, dict):raise ValueError('Unexpected gear item')
        identity = uuid.UUID(str(row.get('uuid', ''))).hex
        if identity in items:raise ValueError('Duplicate gear identity')
        name = next((_text(row.get(key)) for key in ('displayName','name','gearName','customMakeModel') if _text(row.get(key))), '')
        if not name:name = ' '.join(filter(None, (_text(row.get('gearMakeName',row.get('brand'))), _text(row.get('gearModelName',row.get('model')))))) or 'Gear'
        items[identity] = dict(id=identity, name=name, type=_text(row.get('gearTypeName', row.get('gearType'))),
                               status=_text(row.get('gearStatusName', row.get('gearStatus'))))
    return sorted(items.values(), key=lambda item:item['id'])


def _fetch_links(client, identity, known, job):
    """Never treat the endpoint's first-page/default limit as complete history."""
    linked, seen = set(), set()
    url = '/activitylist-service/activities/' + identity + '/gear'
    for page in range(500):
        raw = job.request(lambda:client.connectapi(url, params={'start':page*PAGE_SIZE, 'limit':PAGE_SIZE}), 'Gear activity links')
        if not isinstance(raw, list) or len(raw) > PAGE_SIZE:
            raise ValueError('Unexpected gear activity page')
        ids = []
        for row in raw:
            if not isinstance(row, dict) or 'activityId' not in row:raise ValueError('Unexpected gear activity')
            ids.append(_identity(row['activityId']))
        if len(set(ids)) != len(ids) or seen.intersection(ids):
            raise ValueError('Gear activity pages overlap; sync again')
        seen.update(ids)
        linked.update(known.intersection(ids))
        if len(raw) < PAGE_SIZE:return sorted(linked, key=int)
        job.wait(.2)
    raise ValueError('Gear activity history exceeded the paging limit')


def _publish(cache, items, known, scope, now, generation=0):
    """Publish confirmed empty lists only after every gear list covers this activity set."""
    by_activity = {identity:[] for identity in known}
    complete, stamps = True, []
    for item in items:
        entry = cache.detail(item['id'], LINKS)[1]
        if not entry or entry.get('scope') != scope or entry.get('checked_at', 0) < generation:
            complete = False
        if not entry:continue
        stamps.append(entry.get('checked_at', 0))
        for identity in entry.get('activity_ids', []):
            if identity in by_activity:by_activity[identity].append(item)
    for identity, linked in by_activity.items():
        old = cache.detail(identity, ACTIVITY_GEAR)[1]
        if not complete:
            # A failed check must not turn an existing positive into a negative.
            merged = {item['id']:item for item in (old or {}).get('items', [])}
            merged.update({item['id']:item for item in linked})
            linked = sorted(merged.values(), key=lambda item:item['id'])
        payload = dict(items=linked, complete=complete, checked_at=min(stamps) if stamps else now)
        if payload != old:cache.save_detail(identity, ACTIVITY_GEAR, payload)
    return complete


def sync_gear(client, cache, activities, refresh, job, now=None):
    """Backfill saved activities, then refresh links on user sync or after six hours.

    Successfully checked gear items survive a pause/error. A resumed sync reuses
    those completed items; an interrupted item's small paginated list restarts.
    Only activity IDs already present in this app are retained.
    """
    now = time.time() if now is None else now
    known = {_identity(a['activityId']) for a in activities}
    if not known:return
    scope = hashlib.sha256(','.join(sorted(known, key=int)).encode()).hexdigest()
    catalog = cache.meta(CATALOG)
    # A changed catalog may be saved while links are unfinished. Preserve its
    # refresh generation so completed items are not fetched again on resume.
    state = cache.meta('gear_sync_v1') or {}
    continuing = state.get('pending') and state.get('scope') == scope
    due = not catalog or now-catalog.get('checked_at', 0) >= MAX_AGE or (refresh and not continuing)
    if due:
        job('Reading Garmin gear')
        profile = cache.meta('gear_profile_v1') or {}
        profile_id = profile.get('id') or getattr(client, 'profile_id', None)
        if not isinstance(profile_id, int) or isinstance(profile_id, bool) or profile_id <= 0:
            raw = job.request(lambda:client.connectapi('/userprofile-service/socialProfile'), 'Garmin gear profile')
            profile_id = raw.get('profileId') if isinstance(raw, dict) else None
            if not isinstance(profile_id, int) or isinstance(profile_id, bool) or profile_id <= 0:
                raise ValueError('Garmin gear profile unavailable')
        raw = job.request(lambda:client.get_gear(str(profile_id)), 'Garmin gear catalog')
        items = clean_catalog(raw)
        cache.save_meta('gear_profile_v1', dict(id=profile_id))
        catalog = dict(items=items, checked_at=now)
        cache.save_meta(CATALOG, catalog)
        state = dict(scope=scope, pending=True, generation=now)
        cache.save_meta('gear_sync_v1', state)
    else:
        items = catalog['items']
        if not continuing:
            state = dict(scope=scope, pending=True, generation=0)
            cache.save_meta('gear_sync_v1', state)
    try:
        for index, item in enumerate(items):
            job.checkpoint()
            entry = cache.detail(item['id'], LINKS)[1]
            ready = bool(entry and entry.get('scope') == scope and
                         entry.get('checked_at', 0) >= state.get('generation', 0) and
                         now-entry.get('checked_at', 0) < MAX_AGE)
            if ready:continue
            job('Gear activity links · '+str(index+1)+'/'+str(len(items)), index, len(items))
            linked = _fetch_links(client, item['id'], known, job)
            cache.save_detail(item['id'], LINKS, dict(activity_ids=linked, checked_at=now, scope=scope))
    except Exception:
        _publish(cache, items, known, scope, now, state.get('generation', 0))
        raise
    job.checkpoint()
    if not _publish(cache, items, known, scope, now, state.get('generation', 0)):raise ValueError('Gear sync incomplete')
    state.update(pending=False, checked_at=now)
    cache.save_meta('gear_sync_v1', state)
    job('Gear saved · '+str(len(known))+' activities', len(known), len(known))


def coverage(cache, rows, enabled=False):
    saved = cache.all_details(ACTIVITY_GEAR)
    done = sum(bool((saved.get(r['id']) or {}).get('complete')) for r in rows)
    return dict(done=done, total=len(rows), pending=len(rows)-done, enabled=bool(enabled))
