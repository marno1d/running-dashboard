"""Small explicit diagnostic report; never accepts cached sessions or credentials."""
def validate_diagnostics(payload):
    if not isinstance(payload,dict) or set(payload)!={'schema','kind','report','android_api','max_heap_mb'}:
        raise ValueError('Invalid diagnostic fields')
    if payload['schema']!=1 or payload['kind']!='diagnostics':raise ValueError('Invalid diagnostic format')
    if not isinstance(payload['report'],str) or not 0<len(payload['report'])<=65536:raise ValueError('Invalid diagnostic text')
    for key,low,high in (('android_api',26,100),('max_heap_mb',1,65536)):
        value=payload[key]
        if isinstance(value,bool) or not isinstance(value,int) or not low<=value<=high:raise ValueError('Invalid diagnostic metadata')
    return payload
