"""Verify the service's lifecycle policy using the Java class packaged in the APK."""
from build_apk import run, JAVA, BUILD, ROOT

output=BUILD/'sync-test'
output.mkdir(exist_ok=True)
run(JAVA/'javac','-cp',BUILD/'classes','-d',output,
    ROOT/'tests/java/dev/rundashboard/app/SyncLifecycleTest.java')
run(JAVA/'java','-cp',str(BUILD/'classes')+':'+str(output),
    'dev.rundashboard.app.SyncLifecycleTest')
