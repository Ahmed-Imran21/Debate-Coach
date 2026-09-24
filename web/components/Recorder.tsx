"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

import {
  ApiError,
  createSession,
  putToSignedUrl,
  startSession,
  uploadAndStart,
  type VideoFinalize,
} from "@/lib/api";
import { formatClock } from "@/components/SpeechTrack";
import ConsentPanel from "@/components/video-analysis/ConsentPanel";
import SetupScreen from "@/components/video-analysis/SetupScreen";
import { getVideoAnalysisConsent, type ConsentChoice } from "@/features/video-analysis/consent";
import { cleanupOldTracks, deleteTrack, saveTrackSafely } from "@/features/video-analysis/storage";
import type { Context, VisualSignalTrack } from "@/features/video-analysis/types";
import { uploadTrackWithRetry } from "@/features/video-analysis/upload";
import { useVisualCapture } from "@/features/video-analysis/useVisualCapture";

type Phase = "idle" | "consent" | "setup" | "recording" | "review" | "uploading";

const VIDEO_ANALYSIS_ENABLED = process.env.NEXT_PUBLIC_VIDEO_ANALYSIS_ENABLED === "true";

/**
 * Picks a container the browser can actually produce. Chrome
 * and Firefox give webm/opus; Safari only offers mp4. The
 * chosen MIME type is what ends up on the blob, and the API
 * signs the upload URL against exactly that value, so it has
 * to be a type the backend accepts.
 */
function pickMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;

  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];

  return candidates.find((type) => MediaRecorder.isTypeSupported(type));
}

export default function Recorder(): ReactElement {
  const router = useRouter();

  const [phase, setPhase] = useState<Phase>("idle");
  const [elapsed, setElapsed] = useState(0);
  const [level, setLevel] = useState(0);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [supported, setSupported] = useState(true);
  const [consent, setConsent] = useState<ConsentChoice | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const frameRef = useRef<number | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Video-analysis state that spans setup -> recording -> stop,
  // used only when VIDEO_ANALYSIS_ENABLED and the user opted in.
  const usingVideoRef = useRef(false);
  const videoContextRef = useRef<Context>({ setting: "camera_audience", uses_notes: false });
  const videoT0MsRef = useRef<number | null>(null);
  const videoOutcomeRef = useRef<VideoFinalize | null>(null);
  const videoTrackReadyRef = useRef<VisualSignalTrack | null>(null);
  // The audio-only MediaStream acquireAndStartSetup() hands back,
  // held here from "setup" until SetupScreen finishes (handleSetupReady)
  // or bails (handleSetupSkip) and actually starts the recorder.
  const pendingAudioStreamRef = useRef<MediaStream | null>(null);
  // onstop fires capture.endRecording() without awaiting it (it's
  // a DOM event handler, not async); submit() awaits this instead
  // of reading videoTrackReadyRef/videoOutcomeRef synchronously, so
  // a fast click on "Analyse this speech" can't race finalization
  // and silently discard a track that just hadn't landed yet.
  const videoFinalizePromiseRef = useRef<Promise<void> | null>(null);

  const capture = useVisualCapture({ enabled: VIDEO_ANALYSIS_ENABLED && consent === "in" });

  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" &&
        Boolean(navigator.mediaDevices?.getUserMedia) &&
        typeof MediaRecorder !== "undefined" &&
        pickMimeType() !== undefined,
    );
    if (VIDEO_ANALYSIS_ENABLED) {
      setConsent(getVideoAnalysisConsent());
    }
  }, []);

  const teardown = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }

    if (tickRef.current !== null) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }

    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;

    void audioContextRef.current?.close();
    audioContextRef.current = null;

    setLevel(0);
  }, []);

  useEffect(() => teardown, [teardown]);

  // Object URLs are not garbage collected on their own. Creating
  // one during render would leak a copy of the recording on every
  // rerender, so it is created once per blob and revoked when the
  // blob is replaced or the component unmounts.
  useEffect(() => {
    if (!blob) {
      setPreviewUrl(null);
      return;
    }

    const url = URL.createObjectURL(blob);
    setPreviewUrl(url);

    return () => URL.revokeObjectURL(url);
  }, [blob]);

  /** Wires up the MediaRecorder against an already-acquired audio-only stream and starts it. Identical regardless of whether video analysis is in play. */
  const armRecorder = useCallback(
    (audioStream: MediaStream, mimeType: string) => {
      streamRef.current = audioStream;
      chunksRef.current = [];

      // Defense in depth: MediaRecorder.start() throws synchronously
      // (it doesn't return a Promise) if audioStream has no live
      // tracks — confirmed possible via a stream-lifecycle bug in
      // handleSetupSkip (fixed alongside this, see abandon()'s
      // keepAudioTrack option), and plausible for other reasons too
      // (mic unplugged mid-flow, browser quirks). Without this catch
      // that throw was uncaught — no user feedback, and everything
      // set up below (AudioContext, the level-meter rAF loop, the
      // elapsed-time interval) was left running with no recorder
      // attached to ever stop it via the normal onstop path.
      try {
        const recorder = new MediaRecorder(audioStream, { mimeType });
        recorderRef.current = recorder;

        recorder.ondataavailable = (event) => {
          if (event.data.size > 0) chunksRef.current.push(event.data);
        };

        recorder.onstart = () => {
          if (usingVideoRef.current) {
            const t0 = performance.now();
            videoT0MsRef.current = t0;
            capture.beginRecording(t0);
          }
        };

        recorder.onstop = () => {
          setBlob(new Blob(chunksRef.current, { type: mimeType }));
          setPhase("review");
          teardown();

          if (usingVideoRef.current && videoT0MsRef.current !== null) {
            const durationS = (performance.now() - videoT0MsRef.current) / 1000;
            videoFinalizePromiseRef.current = capture
              .endRecording(durationS, videoContextRef.current)
              .then((result) => {
                if (result.available) {
                  videoTrackReadyRef.current = result.track;
                } else {
                  videoTrackReadyRef.current = null;
                  videoOutcomeRef.current = { status: "unavailable", reason: result.reason };
                }
              });
          }
        };

        // Level meter. This is the one moving thing on the page and
        // it exists to confirm the microphone is actually picking
        // you up, not for decoration.
        const audioContext = new AudioContext();
        audioContextRef.current = audioContext;

        const analyser = audioContext.createAnalyser();
        analyser.fftSize = 512;
        audioContext.createMediaStreamSource(audioStream).connect(analyser);

        const samples = new Uint8Array(analyser.frequencyBinCount);

        const measure = () => {
          analyser.getByteTimeDomainData(samples);

          let sum = 0;
          for (const sample of samples) {
            const centred = (sample - 128) / 128;
            sum += centred * centred;
          }

          const rms = Math.sqrt(sum / samples.length);
          setLevel(Math.min(100, Math.round(rms * 260)));

          frameRef.current = requestAnimationFrame(measure);
        };

        frameRef.current = requestAnimationFrame(measure);

        const startedAt = Date.now();
        setElapsed(0);
        tickRef.current = setInterval(() => {
          setElapsed(Math.floor((Date.now() - startedAt) / 1000));
        }, 250);

        recorder.start();
        setPhase("recording");
      } catch {
        recorderRef.current = null;
        teardown(); // safely no-ops on whatever wasn't reached yet — every ref is null-checked
        setError("Could not start recording. Try again.");
        setPhase("idle");
      }
    },
    [capture, teardown],
  );

  async function startRecording(): Promise<void> {
    setError(null);

    const mimeType = pickMimeType();

    if (!mimeType) {
      setError(
        "This browser cannot record audio. Try the current version of Chrome, Firefox, Edge or Safari.",
      );
      return;
    }

    usingVideoRef.current = false;
    videoTrackReadyRef.current = null;
    videoOutcomeRef.current = null;
    videoT0MsRef.current = null;

    if (VIDEO_ANALYSIS_ENABLED && consent === null) {
      setPhase("consent");
      return;
    }

    if (VIDEO_ANALYSIS_ENABLED && consent === "in") {
      usingVideoRef.current = true;
      setPhase("setup");
      const result = await capture.acquireAndStartSetup();
      if (!result.ok || !result.audioStream) {
        // Camera denied / unsupported: fall back to audio only,
        // exactly like today, but remember why for finalize().
        usingVideoRef.current = false;
        videoOutcomeRef.current = { status: "unavailable", reason: result.reason ?? "camera_denied" };
        await beginAudioOnly(mimeType);
        return;
      }
      // Stay on "setup" phase; SetupScreen drives the rest and
      // triggers armRecorder() via handleSetupReady/handleSetupSkip,
      // which read the stream back out of this ref.
      pendingAudioStreamRef.current = result.audioStream;
      return;
    }

    await beginAudioOnly(mimeType);
  }

  async function beginAudioOnly(mimeType: string): Promise<void> {
    let stream: MediaStream;

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError(
        "Microphone access was blocked. Allow it for this site in your browser settings, then try again.",
      );
      setPhase("idle");
      return;
    }

    armRecorder(stream, mimeType);
  }

  function handleConsentDecided(choice: ConsentChoice): void {
    setConsent(choice);
    setPhase("idle");
    // Let the user press "Start recording" again now that their
    // choice is remembered, rather than acquiring the camera as a
    // side effect of answering the consent question.
  }

  async function handleSetupReady(context: Context): Promise<void> {
    videoContextRef.current = context;
    const mimeType = pickMimeType();
    if (!mimeType) return; // startRecording() already checked this; unreachable in practice

    // The audio stream was acquired back in acquireAndStartSetup();
    // fetch a fresh MediaStream over the same underlying track by
    // re-deriving it isn't possible here, so acquireAndStartSetup
    // returns it directly and we stash it for this moment instead.
    const audioStream = pendingAudioStreamRef.current;
    pendingAudioStreamRef.current = null;
    if (!audioStream) {
      setError("Could not start the recorder. Try again.");
      setPhase("idle");
      return;
    }

    armRecorder(audioStream, mimeType);
  }

  function handleSetupSkip(): void {
    usingVideoRef.current = false;
    videoOutcomeRef.current = {
      status: "unavailable",
      reason: capture.unavailableReason ?? "user_opted_out",
    };
    // keepAudioTrack: true — every onSkip caller (the two manual
    // "Skip visual feedback" buttons and the too-slow-benchmark
    // auto-skip) falls through to armRecorder() below and keeps
    // recording audio-only, same as camera_denied/model_load_failed
    // elsewhere. Without this, abandon() stopped every track on the
    // combined stream, including the audio track armRecorder is
    // about to start a MediaRecorder on two lines down — which threw
    // "The MediaStream is inactive" every single time (confirmed:
    // pendingAudioStreamRef's MediaStream wraps the same live audio
    // track object(s) as the one abandon() was stopping, not a copy).
    capture.abandon(capture.unavailableReason ?? "user_opted_out", { keepAudioTrack: true });

    const audioStream = pendingAudioStreamRef.current;
    pendingAudioStreamRef.current = null;
    const mimeType = pickMimeType();

    if (audioStream && mimeType) {
      armRecorder(audioStream, mimeType);
    } else {
      setPhase("idle");
    }
  }

  function stopRecording(): void {
    recorderRef.current?.stop();
    recorderRef.current = null;
  }

  function discard(): void {
    setBlob(null);
    setElapsed(0);
    setError(null);
    setPhase("idle");
  }

  async function submit(): Promise<void> {
    if (!blob) return;

    setError(null);
    setPhase("uploading");

    try {
      if (!usingVideoRef.current && videoOutcomeRef.current === null) {
        // No video analysis was ever in play: the exact path this
        // app has always used.
        const id = await uploadAndStart(blob, title.trim() || null);
        router.push(`/practice/${id}`);
        return;
      }

      // Video was requested (whether or not it ended up available):
      // the session needs to be created with video_analysis so the
      // backend knows to expect (or account for the absence of) a
      // signal track.
      const contentType = blob.type.split(";")[0] || "audio/webm";
      const created = await createSession({
        content_type: contentType,
        title: title.trim() || null,
        video_analysis: "requested",
      });

      await putToSignedUrl(created.upload_url, created.upload_headers, blob);

      // Make sure onstop's finalization (building the track,
      // closing the extractor) has actually finished before
      // reading its result below.
      if (videoFinalizePromiseRef.current) {
        await videoFinalizePromiseRef.current;
      }

      let finalize: VideoFinalize;

      if (videoTrackReadyRef.current) {
        try {
          await saveTrackSafely(created.id, videoTrackReadyRef.current);
          const track = { ...videoTrackReadyRef.current, session_id: created.id };
          await uploadTrackWithRetry(created.id, track);
          finalize = { status: "uploaded" };
          await deleteTrack(created.id).catch(() => {});
        } catch {
          // uploadTrackWithRetry has already exhausted its own
          // retry/backoff by the time it throws.
          finalize = { status: "unavailable", reason: "upload_failed" };
        }
      } else if (videoOutcomeRef.current) {
        finalize = videoOutcomeRef.current;
      } else {
        finalize = { status: "unavailable", reason: "face_not_found" };
      }

      await startSession(created.id, finalize);
      router.push(`/practice/${created.id}`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The recording could not be sent. Check your connection and try again.",
      );
      setPhase("review");
    }
  }

  // §4.11.6: on app load, clean up IndexedDB entries older than
  // INDEXEDDB_MAX_AGE_DAYS. A track only lives there between
  // "recording stopped" and "upload acknowledged" (submit() itself
  // deletes it on success), so anything this old belongs to a visit
  // that was abandoned before submitting, not an in-flight upload
  // worth resuming — there is no session id to resume it against
  // once the page has reloaded.
  useEffect(() => {
    if (!VIDEO_ANALYSIS_ENABLED) return;
    void cleanupOldTracks();
  }, []);

  if (!supported) {
    return (
      <div className="recorder">
        <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.5rem" }}>
          Recording is not available here
        </h2>
        <p className="note" style={{ margin: 0 }}>
          This browser does not support in-page audio recording. Open
          Debate Coach in the current version of Chrome, Firefox, Edge or
          Safari.
        </p>
      </div>
    );
  }

  // The camera is live for exactly these phases. Outside them the
  // stream is already stopped, so there is no frame loop left to
  // protect and display:none is safe.
  const cameraLive = phase === "setup" || phase === "recording";
  // During setup the preview is the whole point (you can't act on
  // "move closer" without it). During recording it's opt-in.
  const previewVisible = phase === "setup" || capture.showPreview;

  return (
    <div className="recorder">
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {/*
        The ONE camera preview element for the whole recorder. It is
        rendered unconditionally, outside every {phase === "..."}
        block, and it must stay that way.

        Two separate bugs (both 2026-09-18/19) came from this element
        being rendered by phase-scoped parents, so that a phase change
        swapped it for a different DOM node:

          idle -> setup:      no <video> existed during setup at all,
                              so capture.videoRef.current was null,
                              acquireAndStartSetup()'s
                              `if (videoRef.current) { srcObject = ... }`
                              never ran, and loopStep()'s `!video`
                              guard killed the loop before it started.
          setup -> recording: SetupScreen's <video> unmounted and
                              Recorder's mounted — a different node
                              with no srcObject. The rVFC chain was
                              anchored to the destroyed element, and
                              loopStep() is only ever re-armed from
                              inside its own callback, so the loop
                              died silently. Zero frames were
                              collected, endRecording() reported
                              face_not_found, and the report said the
                              user's face was never found.

        srcObject is assigned exactly once, in acquireAndStartSetup().
        Nothing reassigns it on a phase change. So if this element is
        ever swapped for a different node mid-session, the camera feed
        and the frame loop are both silently lost, with no error.

        Equally important: never use `hidden` / display:none while
        cameraLive is true. requestVideoFrameCallback only fires for
        frames presented for composition, so a display:none video
        stops the loop just as dead as unmounting it. Hide it with
        opacity instead, which keeps it composited.

        If you add a phase that needs the camera, add it to
        cameraLive above — do not render a second <video> element.
      */}
      <video
        ref={capture.videoRef}
        muted
        playsInline
        autoPlay
        style={{
          display: cameraLive ? "block" : "none",
          opacity: previewVisible ? 1 : 0,
          // Out of flow when invisible so it leaves no layout gap,
          // but still composited (unlike display:none) so rVFC keeps
          // firing and the frame loop keeps running.
          position: previewVisible ? "static" : "absolute",
          pointerEvents: previewVisible ? "auto" : "none",
          width: phase === "setup" ? "100%" : "8rem",
          maxWidth: "34rem",
          aspectRatio: "16 / 9",
          objectFit: "cover",
          transform: "scaleX(-1)",
          borderRadius: "var(--radius)",
          background: "var(--well)",
          marginBottom: previewVisible ? "1.25rem" : 0,
        }}
      />

      {phase === "idle" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.5rem" }}>
            Record a speech
          </h2>
          <p className="note" style={{ marginBottom: "1.5rem" }}>
            Speak as you would in a round. Your browser will ask for
            microphone access the first time.
            {VIDEO_ANALYSIS_ENABLED && consent === "in" && " Visual feedback is on."}
            {VIDEO_ANALYSIS_ENABLED && consent === "out" && " Visual feedback is off."}
          </p>
          <div className="btn-row">
            <button className="btn" type="button" onClick={startRecording}>
              Start recording
            </button>
            {VIDEO_ANALYSIS_ENABLED && consent !== null && (
              <button
                className="btn btn-quiet"
                type="button"
                onClick={() => setPhase("consent")}
              >
                Change visual feedback setting
              </button>
            )}
          </div>
        </>
      )}

      {phase === "consent" && (
        <ConsentPanel onDecide={handleConsentDecided} />
      )}

      {phase === "setup" && (
        <SetupScreen capture={capture} onReady={handleSetupReady} onSkip={handleSetupSkip} />
      )}

      {phase === "recording" && (
        <>
          <p className="timer" aria-live="off">
            {formatClock(elapsed)}
          </p>

          <div className="meter" aria-hidden="true">
            <div className="meter-fill" style={{ width: `${level}%` }} />
          </div>

          <p className="sr-only" role="status">
            Recording in progress.
          </p>

          {usingVideoRef.current && capture.faceMissingSeconds > 0 && (
            <p className="note" role="status" style={{ marginBottom: "1rem" }}>
              Your face isn&apos;t in view.
            </p>
          )}

          {usingVideoRef.current && (
            <div className="btn-row" style={{ marginBottom: "1rem" }}>
              <button
                className="filter"
                type="button"
                aria-pressed={capture.showPreview}
                onClick={() => capture.setShowPreview(!capture.showPreview)}
              >
                {capture.showPreview ? "Hide camera preview" : "Show camera preview"}
              </button>
            </div>
          )}

          {/* The camera preview lives at the top of this component,
              outside every phase block — see the comment there. It
              must not be rendered here too. */}

          <button className="btn btn-stop" type="button" onClick={stopRecording}>
            Stop recording
          </button>
        </>
      )}

      {(phase === "review" || phase === "uploading") && blob && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.5rem" }}>
            Recording of {formatClock(elapsed)}
          </h2>

          {previewUrl && (
            <audio
              controls
              src={previewUrl}
              style={{ width: "100%", margin: "1rem 0 1.25rem" }}
            />
          )}

          <label className="field">
            <span>Name this session (optional)</span>
            <input
              type="text"
              maxLength={200}
              placeholder="Second constructive, nuclear energy"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              disabled={phase === "uploading"}
            />
          </label>

          <div className="btn-row">
            <button
              className="btn"
              type="button"
              onClick={submit}
              disabled={phase === "uploading"}
            >
              {phase === "uploading" ? "Sending" : "Analyse this speech"}
            </button>

            <button
              className="btn btn-quiet"
              type="button"
              onClick={discard}
              disabled={phase === "uploading"}
            >
              Record again
            </button>
          </div>
        </>
      )}
    </div>
  );
}
