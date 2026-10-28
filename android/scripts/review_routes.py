"""Summarize exported elevation inputs without fetching or changing any recordings."""
from pathlib import Path
import math
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT.parent/'common'),str(ROOT/'app/src/main/python')]
from route_review_contract import validate_review
from route_workouts import RoutePath,average_rates


def report(payload):
    validate_review(payload)
    activities={str(row['activityId']):row for row in payload['activities']}
    dates=sorted(row.get('startTimeLocal','')[:10] for row in payload['activities'])
    lines=['# Route elevation review','',
        f"App {payload.get('app_version','unknown')} · {len(activities)} saved sessions · {len(payload['routes'])} routes",'']
    if dates:lines.append(f'Saved session dates: {dates[0]} to {dates[-1]}.')
    lines.extend(['All distances below are miles; gain/loss are feet. Rates are feet per mile.',
        'This report compares saved inputs; it does not download or modify sessions.',''])
    settings=payload['settings']
    lines.extend([f"Current conditions: +{settings.get('target_gain_per_mile',0)} / −{settings.get('target_loss_per_mile',0)} ft/mi.",
        f"Selected route: {settings.get('target_route_name','Manual')} · engine {settings.get('target_route_engine','manual')}",''])
    for route in payload['routes']:
        lines.extend(['## '+route['name'],f"{route['shape']} · {route['surface']} · reversed: {route.get('reverse',False)}",''])
        ref=route.get('reference')
        if not ref:lines.extend(['No reference selected.','']);continue
        lines.append(f"Reference: {ref.get('date','')} · {ref.get('title','')} · session {ref['id']}")
        if ref.get('stale'):lines.append('Check: this reference is marked stale.')
        activity=activities.get(ref['id'],{})
        distance=activity.get('distance')
        gain=activity.get('elevationGain');loss=activity.get('elevationLoss')
        if distance:
            recorded=f"Saved activity distance: {distance/1609.344:.3f} mi."
            if isinstance(gain,(int,float)) and isinstance(loss,(int,float)):
                recorded+=f" Garmin totals: +{gain/.3048:.1f} / −{loss/.3048:.1f} ft; +{gain/.3048/(distance/1609.344):.1f} / −{loss/.3048/(distance/1609.344):.1f} ft/mi."
            lines.append(recorded)
        data=payload['reference_recordings'].get(ref['id'])
        if not data or len(data.get('profile',[]))<2:
            lines.extend(['Check: no cached elevation profile is available.','']);continue
        try:
            full=RoutePath(data['profile']);length,up,down=full.profile[-1]
            source=data.get('source','legacy watch altitude')
            lines.append(f"Full reference ({source}): {length/1609.344:.3f} mi · +{up/.3048:.1f} / −{down/.3048:.1f} ft.")
            path=RoutePath(data['profile'],route['shape'],route.get('extent'),route.get('reverse',False))
            course=path.extent*(2 if route['shape']=='out_back' else 1);course_up,course_down=path.delta(0,course)
            course_label='First measured lap (before combining laps and balancing closure)' if route['shape']=='loop' else 'Configured course'
            lines.append(f"{course_label}: {course/1609.344:.3f} mi · +{course_up/.3048:.1f} / −{course_down/.3048:.1f} ft.")
            lines.append(f"Extent/turn distance: {path.extent/1609.344:.3f} mi. GPS suggested turn: {data.get('suggested_turn')} m; suggested loop: {data.get('suggested_loop')} m.")
            rates=average_rates(route,data)
            lines.append(f"Expected route averages: +{rates['gain_per_mile']:.1f} / −{rates['loss_per_mile']:.1f} ft/mi.")
            if distance and abs(length-distance)>max(50,distance*.01):lines.append('Check: saved activity and elevation-profile distances differ by more than 1% or 50 m.')
            if str(source).startswith('opentopodata:'):
                terrain=payload.get('details',{}).get('terrain_v1',{}).get(ref['id'],{})
                for label,actual,key in (('ascent',up,'elevation_gain'),('descent',down,'elevation_loss')):
                    saved=terrain.get(key)
                    if isinstance(saved,(int,float)) and abs(actual-saved)>.11:lines.append(f'Check: downloaded terrain {label} differs between the saved profile and session totals.')
            else:
                if isinstance(gain,(int,float)) and abs(up-gain)>max(10,abs(gain)*.15):lines.append('Check: Garmin ascent and the smoothed profile ascent differ by more than 15% or 10 m.')
                if isinstance(loss,(int,float)) and abs(down-loss)>max(10,abs(loss)*.15):lines.append('Check: Garmin descent and the smoothed profile descent differ by more than 15% or 10 m.')
            if settings.get('target_route_id')==route['id']:
                for key,field in (('gain_per_mile','target_gain_per_mile'),('loss_per_mile','target_loss_per_mile')):
                    try:same=math.isclose(float(settings.get(field,0) or 0),rates[key],abs_tol=.05)
                    except (TypeError,ValueError):same=False
                    if not same:lines.append(f'Check: the saved {field} does not match the selected route’s calculated average.')
        except (ValueError,TypeError,KeyError,IndexError) as error:
            lines.append('Check: the saved profile/course could not be evaluated ('+type(error).__name__+').')
        lines.append('')
    return '\n'.join(lines)+'\n'
