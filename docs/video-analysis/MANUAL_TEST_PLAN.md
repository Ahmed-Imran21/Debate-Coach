# Manual test plan

None of this can be verified by an automated test, because it depends on a real camera,
a real face, and real network conditions. Do this before trusting the feature with real
users. Run it against a local dev build first (`NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED=true`,
`NEXT_PUBLIC_VISION_DEBUG=true` so `/dev/vision-debug` is reachable), then again against
whatever environment will actually serve users.

## 1. Sign verification (the debug page)

Open `/dev/vision-debug`, allow the camera, and work through its on-screen checklist:

| Action | Expect |
|---|---|
| Face still, looking at the lens | `yaw`/`pitch`/`roll` all near 0 |
| Turn head to your own right | `yaw` increases |
| Turn head to your own left | `yaw` decreases |
| Look up (head only, eyes with it) | `pitch` increases |
| Look down | `pitch` decreases |
| Tilt head toward your right shoulder | `roll` increases |
| Look right with eyes only, head still | `iris_x` increases |
| Look up with eyes only | `iris_y` increases |
| Close both eyes for ~1s | `iris_x`/`iris_y` show `-` (null), not 0 |
| Raise your right hand | `rh_present` becomes 1, `lh_present` stays 0 |
| Raise your left hand instead | `lh_present` becomes 1, `rh_present` stays 0 |
| Raise both hands | both present; centroids roughly mirror each other horizontally |

If any angle is inverted: flip the matching constant in
`web/features/video-analysis/math.ts` (`YAW_SIGN`, `PITCH_SIGN`, or `ROLL_SIGN` — each is
a standalone `1`/`-1`). If handedness is swapped: the calibration step's one-retry flip
(`resolveHandSideFromLabel`) should already catch this during a real recording's setup
screen; if it's wrong even after that, check `HANDEDNESS_LABEL_INVERTED_DEFAULT` in
`web/features/video-analysis/config.ts`.

Also note on this pass: the device tier the benchmark landed on, the effective fps shown,
and the p90 inference latency, for comparison against the browser matrix below.

## 2. Clock offset (the clap test)

Audio and video are timestamped independently (the recorder's `onstart` event vs. each
video frame's own capture timestamp) and never share a hardware clock, so any consistent
offset between them needs to be measured, not assumed to be zero.

Procedure, repeat 5 times per browser:
1. Open the debug page (or record a real session with the camera preview visible).
2. Start recording.
3. Wait ~2 seconds, then clap once, sharply, with your hands clearly in frame.
4. Keep recording for ~2 more seconds, then stop.
5. From the recording: find the audio sample where the clap's transient starts (zoom in
   on the waveform in any audio editor, or use the browser's own player and scrub by ear).
6. From the video signals: find the frame where the hands are at their closest point
   (the `hand_speed` readout should peak right at the moment of contact, then drop as the
   hands separate again).
7. Record `video_time_of_contact - audio_time_of_contact` in seconds.

Record the 5 offsets (per browser) in a table like:

| Browser | Trial 1 | Trial 2 | Trial 3 | Trial 4 | Trial 5 | Mean |
|---|---|---|---|---|---|---|
| Chrome desktop | | | | | | |
| Edge desktop | | | | | | |
| Firefox desktop | | | | | | |
| Safari desktop | | | | | | |
| Chrome Android | | | | | | |

If the mean offset is consistently non-zero and stable (not just noise), set
`CLOCK_OFFSET_S` in `web/features/video-analysis/config.ts` to correct for it. If it
varies a lot between trials, that's a real synchronization problem worth its own
investigation before shipping — a large `clock_uncertainty_ms` already downgrades
correlated-moment generation (see `CLOCK_UNCERTAINTY_MAX_MS_FOR_MOMENTS` in
`visual_analysis/config.py`), but a *biased* offset (consistently early or late, not just
noisy) isn't something that constant protects against.

## 3. Browser matrix

For each browser, run a real ~60-90 second recording (opt in, complete setup, speak,
stop, submit) and record:

| Browser | Device tier reached | Effective fps (face) | p90 latency (ms) | Notes |
|---|---|---|---|---|
| Chrome desktop | | | | |
| Edge desktop | | | | |
| Firefox desktop | | | | |
| Safari desktop | | | | |
| Chrome Android | | | | |

Confirm for each: the setup screen completes, the recording finishes, the upload
succeeds, and the report page eventually shows a "Visual delivery" section (state may be
`processed`, `partial`, or `insufficient_data` depending on the device — any of those is a
pass; `failed` or the page never updating is not).

## 4. Lighting and framing scenarios

Each of these should complete setup (possibly with a warning) and produce a report with
plausible metrics — not a crash, not a stuck "in progress" state.

- **Normal desk lighting, ~50cm from camera.** Baseline case; expect `full` or `reduced`
  tier, high coverage, no framing warnings.
- **Backlit** (bright window or light directly behind you). Setup screen should show the
  `backlit` lighting state; confirm it doesn't block you from continuing.
- **Dim room** (main light off, only ambient light). Setup screen should show `dim`;
  confirm the framing hint text is calm, not alarming.
- **Too close** (face fills most of the frame). Setup should suggest moving back.
- **Too far** (whole upper body visible, hands small in frame). Setup should suggest
  moving closer.
- **Face leaves the frame for 5+ seconds mid-recording.** Confirm the "Your face isn't in
  view" hint appears after ~3 seconds and clears once your face returns; confirm the
  report afterward shows a `face_lost` event and reduced `face_tracked_ratio`.

## 5. Second person

With another person visible in frame alongside you for at least 20-30 seconds of a
recording: confirm the report's Visual delivery section shows the
`second_person_detected` warning, and that metric confidence in that report reads `Low`
across the board (not just the metrics that obviously involve a second face) — this is a
deliberate session-wide cap, not a per-metric check.

## 6. Tab switching mid-recording

Start a recording, switch to a different browser tab for 5-10 seconds, switch back,
finish and submit. Confirm the session still completes normally and the report's visual
metrics look reasonable for the time actually spent visible (the hidden interval should
not silently count as "camera facing" or "hands still" — coverage ratios should reflect
only the visible portion).

## 7. Offline / upload recovery

1. Start a recording with visual feedback on, speak for ~20 seconds, stop.
2. Before pressing "Analyse this speech", disconnect from the network (turn off wifi, or
   use devtools to go offline).
3. Press "Analyse this speech". Confirm it fails gracefully (an error message, not a
   silent hang) and that reconnecting and retrying works.
4. Repeat, but reconnect network mid-upload instead of before pressing submit — confirm
   the retry/backoff in `uploadTrackWithRetry` recovers without you needing to re-record.
5. Force a failure that exhausts all retries (e.g. block the signal-upload endpoint
   specifically in devtools' network conditions/request blocking, so audio still
   succeeds). Confirm: the audio session still completes and shows results; the video
   status shows `unavailable` with reason `upload_failed`; nothing was lost that a normal
   audio-only session wouldn't have produced anyway.
