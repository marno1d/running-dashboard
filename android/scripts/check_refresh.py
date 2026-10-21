"""Verify the pull-to-refresh decisions used by the native gesture wrapper."""
from build_apk import run, JAVA, BUILD, ROOT

output = BUILD / 'refresh-test'
output.mkdir(exist_ok=True)
run(JAVA / 'javac', '-d', output,
    ROOT / 'app/src/dev/rundashboard/app/PullRefreshGesture.java',
    ROOT / 'tests/java/dev/rundashboard/app/PullRefreshGestureTest.java')
run(JAVA / 'java', '-cp', output, 'dev.rundashboard.app.PullRefreshGestureTest')
