import type { ReactElement } from "react";

export type MarkKind = "pause" | "filler" | "stutter" | "fallacy";

export interface Mark {
  at: number;
  kind: MarkKind;
  span?: number;
}

const COLOR: Record<MarkKind, string> = {
  pause: "var(--rule-strong)",
  filler: "var(--amber)",
  stutter: "var(--ink-faint)",
  fallacy: "var(--brick)",
};

const KIND_LABEL: Record<MarkKind, string> = {
  pause: "Pause over one second",
  filler: "Filler word",
  stutter: "Stutter",
  fallacy: "Flagged fallacy",
};

export function formatClock(seconds: number): string {
  const safe = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

interface Props {
  duration: number;
  marks: Mark[];
  title: string;
  caption?: string;
}

/**
 * A debate speech is a measured stretch of time, and every
 * finding this tool produces is anchored to a moment in it. So
 * the axis is the primary way of showing a session: minute
 * ticks along a baseline, with each finding placed where it
 * happened rather than listed out of order.
 *
 * Rendered as inline SVG at a fixed viewBox and scaled by CSS,
 * so it stays sharp and needs no measurement on the client.
 */
export default function SpeechTrack({
  duration,
  marks,
  title,
  caption,
}: Props): ReactElement {
  const WIDTH = 900;
  const HEIGHT = 96;
  const PAD = 8;
  const BASE = 64;
  const usable = WIDTH - PAD * 2;

  const safeDuration = duration > 0 ? duration : 1;
  const x = (t: number) =>
    PAD + (Math.min(Math.max(t, 0), safeDuration) / safeDuration) * usable;

  // A tick every 30 seconds for short speeches, every minute
  // beyond four minutes, so the axis never crowds.
  const step = safeDuration > 240 ? 60 : 30;
  const ticks: number[] = [];
  for (let t = 0; t <= safeDuration; t += step) ticks.push(t);

  const present = Array.from(new Set(marks.map((m) => m.kind)));

  return (
    <figure className="track" style={{ margin: 0 }}>
      <div className="track-head">
        <span className="track-title">{title}</span>
        <span className="note">Length {formatClock(safeDuration)}</span>
      </div>

      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        role="img"
        aria-label={`${title}. ${marks.length} findings across ${formatClock(
          safeDuration,
        )}.`}
        preserveAspectRatio="none"
      >
        {/* Speech body */}
        <rect
          x={PAD}
          y={28}
          width={usable}
          height={16}
          fill="var(--well)"
          rx="1"
        />

        {/* Findings */}
        {marks.map((mark, index) => {
          const left = x(mark.at);
          const width = mark.span
            ? Math.max(2, x(mark.at + mark.span) - left)
            : 2;

          return (
            <rect
              key={`${mark.kind}-${index}`}
              x={left}
              y={mark.kind === "pause" ? 28 : 20}
              width={width}
              height={mark.kind === "pause" ? 16 : 32}
              fill={COLOR[mark.kind]}
            />
          );
        })}

        {/* Baseline */}
        <line
          x1={PAD}
          y1={BASE}
          x2={WIDTH - PAD}
          y2={BASE}
          stroke="var(--rule-strong)"
          strokeWidth="1"
        />

        {/* Minute ticks */}
        {ticks.map((t) => (
          <g key={t}>
            <line
              x1={x(t)}
              y1={BASE}
              x2={x(t)}
              y2={BASE + (t % 60 === 0 ? 8 : 4)}
              stroke="var(--rule-strong)"
              strokeWidth="1"
            />
            {t % 60 === 0 && (
              <text
                x={x(t)}
                y={BASE + 24}
                fill="var(--ink-faint)"
                fontSize="13"
                textAnchor={t === 0 ? "start" : "middle"}
              >
                {formatClock(t)}
              </text>
            )}
          </g>
        ))}
      </svg>

      {present.length > 0 && (
        <div className="legend">
          {present.map((kind) => (
            <span key={kind}>
              <i style={{ background: COLOR[kind] }} aria-hidden="true" />
              {KIND_LABEL[kind]}
            </span>
          ))}
        </div>
      )}

      {caption && <figcaption className="note">{caption}</figcaption>}
    </figure>
  );
}
