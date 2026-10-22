"""Verify inline conditions and manual weather hold without Android or a network."""
from build_apk import run, JAVA, BUILD, ROOT
output=BUILD/'conditions-test';output.mkdir(exist_ok=True)
run(JAVA/'javac','-d',output,
    ROOT/'app/src/dev/rundashboard/app/TargetConditions.java',
    ROOT/'app/src/dev/rundashboard/app/WeatherPolicy.java',
    ROOT/'app/src/dev/rundashboard/app/WeatherData.java',
    ROOT/'tests/java/dev/rundashboard/app/TargetConditionsTest.java',
    ROOT/'tests/java/dev/rundashboard/app/WeatherDataTest.java')
run(JAVA/'java','-cp',output,'dev.rundashboard.app.TargetConditionsTest')
run(JAVA/'java','-cp',output,'dev.rundashboard.app.WeatherDataTest')
