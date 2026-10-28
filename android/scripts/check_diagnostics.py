"""Check persistent crash context and redaction without Android or network access."""
from build_apk import run,JAVA,BUILD,ROOT
output=BUILD/'diagnostic-test';output.mkdir(exist_ok=True)
run(JAVA/'javac','-d',output,ROOT/'app/src/dev/rundashboard/app/AppErrorLog.java',ROOT/'tests/java/dev/rundashboard/app/AppErrorLogTest.java')
run(JAVA/'java','-cp',output,'dev.rundashboard.app.AppErrorLogTest')
