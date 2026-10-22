"""Optional live Open-Meteo contract check using its public Berlin example, never phone location."""
import json
import time
import urllib.request

url=('https://api.open-meteo.com/v1/forecast?latitude=52.52&longitude=13.41'
     '&current=temperature_2m,relative_humidity_2m&temperature_unit=fahrenheit'
     '&timeformat=unixtime&forecast_days=1')
with urllib.request.urlopen(url,timeout=15) as response:
    data=json.load(response)
current,units=data['current'],data['current_units']
assert units['temperature_2m']=='°F',units
assert units['relative_humidity_2m']=='%',units
assert -150<=current['temperature_2m']<=160,current
assert 0<=current['relative_humidity_2m']<=100,current
assert -900<=time.time()-current['time']<=7200,current
print('Open-Meteo public example: HTTPS current temperature/humidity, Fahrenheit units and Unix model time: OK')
