"""Synthetic terrain service; never reads watch altitude or accesses a network."""
def elevations(samples,args,**kwargs):
    result=[]
    for sample in samples:
        distance=sample['distanceMeters']%6000
        height=100+min(distance,6000-distance)/10
        result.append(dict(sample,elevationMeters=height,dataset='synthetic'))
    return result
