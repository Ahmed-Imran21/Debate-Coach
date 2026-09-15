"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

import { ApiError, uploadAndStart } from "@/lib/api";
import { formatClock } from "@/components/SpeechTrack";

type Phase = "idle" | "recording" | "review" | "uploading";

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

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const frameRef = useRef<number | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" &&
        Boolean(navigator.mediaDevices?.getUserMedia) &&
        typeof MediaRecorder !== "undefined" &&
        pickMimeType() !== undefined,
    );
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

  async function startRecording(): Promise<void> {
    setError(null);

    const mimeType = pickMimeType();

    if (!mimeType) {
      setError(
        "This browser cannot record audio. Try the current version of Chrome, Firefox, Edge or Safari.",
      );
      return;
    }

    let stream: MediaStream;

    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setError(
        "Microphone access was blocked. Allow it for this site in your browser settings, then try again.",
      );
      return;
    }

    streamRef.current = stream;
    chunksRef.current = [];

    const recorder = new MediaRecorder(stream, { mimeType });
    recorderRef.current = recorder;

    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data);
    };

    recorder.onstop = () => {
      setBlob(new Blob(chunksRef.current, { type: mimeType }));
      setPhase("review");
      teardown();
    };

    // Level meter. This is the one moving thing on the page and
    // it exists to confirm the microphone is actually picking
    // you up, not for decoration.
    const audioContext = new AudioContext();
    audioContextRef.current = audioContext;

    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    audioContext.createMediaStreamSource(stream).connect(analyser);

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
      const id = await uploadAndStart(blob, title.trim() || null);
      router.push(`/practice/${id}`);
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "The recording could not be sent. Check your connection and try again.",
      );
      setPhase("review");
    }
  }

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

  return (
    <div className="recorder">
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {phase === "idle" && (
        <>
          <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.5rem" }}>
            Record a speech
          </h2>
          <p className="note" style={{ marginBottom: "1.5rem" }}>
            Speak as you would in a round. Your browser will ask for
            microphone access the first time.
          </p>
          <button className="btn" type="button" onClick={startRecording}>
            Start recording
          </button>
        </>
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
