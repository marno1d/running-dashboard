# Third-party components

The APK includes the notices in Python distributions' `.dist-info` directories,
as well as notices for its embedded runtime and Termux native libraries.

- [Chaquopy 17.0.0](https://github.com/chaquo/chaquopy/tree/17.0.0), MIT.
- [CPython 3.14.0](https://github.com/python/cpython/tree/v3.14.0), PSF license.
- [python-garminconnect](https://github.com/cyberjunky/python-garminconnect), MIT.
- [fitdecode 0.11.0](https://github.com/polyvertex/fitdecode), MIT.
- Python dependencies and versions are pinned in `requirements.txt`; their
  distribution notices are included in the APK assets.
- [libffi](https://github.com/libffi/libffi), MIT.
- [Termux libandroid-support](https://github.com/termux/libandroid-support),
  includes Apache 2.0 and MIT components; bundled notices identify their authors.
- The embedded CPython distribution includes its own OpenSSL and SQLite native
  libraries. Their notices are included in the CPython license file.

The app is an independent personal prototype and isn't affiliated with Garmin.
