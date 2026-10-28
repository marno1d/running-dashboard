"""Check shared scrubber math without an Android device."""
from build_apk import run,JAVA,BUILD,ROOT
output=BUILD/'workout-trace-test';output.mkdir(exist_ok=True)
run(JAVA/'javac','-d',output,ROOT/'app/src/dev/rundashboard/app/WorkoutTrace.java',ROOT/'tests/java/dev/rundashboard/app/WorkoutTraceTest.java')
run(JAVA/'java','-cp',output,'dev.rundashboard.app.WorkoutTraceTest')
