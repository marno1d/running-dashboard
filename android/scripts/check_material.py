"""Check UI contrast, adaptive button geometry, and readable chart ticks."""
from build_apk import run, JAVA, BUILD, ROOT

output = BUILD / 'material-test'
output.mkdir(exist_ok=True)
checks = ('MaterialPalette', 'ButtonLayout', 'ChartAxis')
run(JAVA / 'javac', '-d', output,
    *[ROOT / f'app/src/dev/rundashboard/app/{name}.java' for name in checks],
    *[ROOT / f'tests/java/dev/rundashboard/app/{name}Test.java' for name in checks])
for name in checks:
    run(JAVA / 'java', '-cp', output, f'dev.rundashboard.app.{name}Test')
