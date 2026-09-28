# Debate Coach for Android

A native Android app (Kotlin, Jetpack Compose, Material 3) for the same
backend, account and data as the website. Everything the website does,
except the admin panel and the profile page.

## Structure

The website's brand (colours, Newsreader and IBM Plex Sans, its calm
tone) on Android's own structure:

- **Navigation**: four destinations in a bottom bar on phones, a
  navigation rail on tablets: *Sessions*, *Progress* (the graph),
  *Insights* (the AI progress report) and *Account*. Record is the
  Sessions screen's floating button (the rail's button on tablets).
  On large tablets Sessions shows the list and a report side by side.
- **Screens**: each destination has a large, collapsing top bar;
  secondary actions sit in its overflow menu. A report has a collapsing
  header (name and overall score) and Overview / Findings / Visual tabs,
  with sharing and PDF export in bottom sheets and a mini-player that
  follows key moments. The recorder is a focused full-screen flow.
- **Motion**: a container transform from a session's row into its
  report, fade through between tabs, the recorder rising from the
  bottom; predictive back throughout.
- **Deep links**: `debatecoach://sessions`, `://session/<id>`,
  `://record`, `://progress`, `://insights`, `://account`; a *Record*
  launcher shortcut while signed in.
- **Design system**: `ui/theme/Theme.kt` (Material 3 colour roles in
  light and dark, type scale, `Space`, `Radius`, `Elevation`, `Motion`,
  window size classes) and `ui/components/`.

## Builds

Two flavours, both installable side by side as debug APKs:

| Flavour | Backend | Website (share links, privacy, terms) | App id |
|---|---|---|---|
| `local` | `-PlocalApiUrl` (default `http://192.168.1.100:8000`) | `-PlocalWebsiteUrl` (default: same host, port 3000) | `com.debatecoach.app.local` |
| `production` | `https://debate-coach-backend-7uc4kfztqq-uc.a.run.app` | `https://web-debate-coach1.vercel.app` | `com.debatecoach.app` |

```bash
cd android
./gradlew assembleLocalDebug -PlocalApiUrl=http://<your-computer's-LAN-IP>:8000
./gradlew assembleProductionDebug
# -> app/build/outputs/apk/{local,production}/debug/*.apk
```

Each build also makes one APK per processor family (`arm64-v8a` for
current phones, `armeabi-v7a` for older 32-bit ones, `x86_64` for
emulators and Chromebooks) and a `universal` one that runs anywhere.

`-PsideBySide=true` gives the build its own app id (`….redesign`), name
("Debate Coach (new)") and deep-link scheme (`debatecoach-new://`), so it
installs next to another build of the app for comparison.

Put `localApiUrl=...` in `~/.gradle/gradle.properties` to stop passing it.
The local build allows plain HTTP (your LAN backend); production is HTTPS
only. The local backend must listen on `0.0.0.0` (uvicorn `--host 0.0.0.0`).

Requirements: JDK 17+ (21 used here) and the Android SDK (platform 37,
build-tools 37.0.0), with `sdk.dir` in `local.properties` or
`ANDROID_HOME` set. The MediaPipe models are fetched at build time from
the same URLs the website uses and checked against the website's
SHA-256s (or copied from `web/public/mediapipe/models` if present).

### Visual feedback flag

Like the website's `NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED`, which must match
the backend's `VIDEO_ANALYSIS_ENABLED`: on in both builds, as it is on
the live backend. If the backend ever turns it off, build with
`-PproductionVideoAnalysis=false` (or `-PlocalVideoAnalysis=false`).

## Install on a phone

1. On the phone: Settings → About phone → tap *Build number* 7 times;
   then Settings → System → Developer options → *USB debugging* on.
2. Connect by USB and accept the prompt, then
   `~/Android/Sdk/platform-tools/adb install -r app/build/outputs/apk/local/debug/app-local-debug.apk`.

   Or copy the APK to the phone and open it (allow installs from that app).

## Tests

```bash
./gradlew :app:testLocalDebugUnitTest          # unit + Compose UI (Robolectric) tests
parity/check-goldens.sh                        # regenerate web-parity goldens and check them
DC_BACKEND_URL=http://localhost:8000 DC_TEST_AUDIO=/path/speech.m4a \
  ./gradlew :app:testLocalDebugUnitTest --tests '*CrossClient*'   # website and app, one account
./gradlew :app:testLocalDebugUnitTest --tests '*Screenshots*' -PscreenshotsDir=/tmp/shots
                                               # every screen to PNG, light and dark, for review
```

## Web parity for the visual signals

`app/src/main/java/com/debatecoach/app/visual/` is a port of
`web/features/video-analysis/`. Parity is tested, not assumed:
`parity/generate-goldens.test.ts` runs the **website's own modules**
(imported unchanged from `web/`) on the inputs of the web's own tests
plus thousands of seeded random ones, and `VisualParityGoldenTest`
requires the Kotlin port to reproduce every output exactly: doubles bit
for bit, built tracks byte for byte against `JSON.stringify`. Where
JavaScript's number semantics differ from Kotlin's (V8's `Math.hypot`,
`Math.round`, the ordering of signed zeros, `Number::toString`),
`JsMath` reproduces JavaScript's.

The app labels its tracks `source.platform: "android"`, which the live
backend accepts.
