"""Verify chart gesture geometry with the same Java classes packaged in the APK."""
from build_apk import run, JAVA, BUILD, ROOT
output=BUILD/'chart-test';output.mkdir(exist_ok=True)
run(JAVA/'javac','-cp',BUILD/'classes','-d',output,ROOT/'tests/java/dev/rundashboard/app/ChartViewportTest.java')
run(JAVA/'java','-cp',str(BUILD/'classes')+':'+str(output),'dev.rundashboard.app.ChartViewportTest')
