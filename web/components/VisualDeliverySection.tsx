import type { ReactElement } from "react";

import {
  CAMERA_FACING_METRIC_KEYS,
  CONFIDENCE_LABEL,
  VIDEO_UNAVAILABLE_REASON_LABEL,
  VISUAL_METRIC_INFO,
  VISUAL_METRIC_ORDER,
  VISUAL_WARNING_LABEL,
  type SessionReport,
  type VisualMetric,
  type VisualMetricFormat,
} from "@/lib/types";

const FACE_GATED_KEYS = new Set([
  "camera_facing_ratio",
  "gaze_away_events_per_min",
  "longest_gaze_away_s",
  "head_down_ratio",
  "head_motion_median_deg_s",
]);

const HAND_GATED_KEYS = new Set([
  "gesture_rate_per_min",
  "gesture_amplitude_median",
  "hands_still_longest_s",
  "hands_still_ratio",
]);

function formatValue(value: number, format: VisualMetricFormat): string {
  switch (format) {
    case "ratio":
      return `${Math.round(value * 100)}%`;
    case "rate":
      return `${value.toFixed(1)}/min`;
    case "seconds":
      return `${value.toFixed(1)}s`;
    case "degrees":
      return `${value.toFixed(1)}°/s`;
    case "amplitude":
      return value.toFixed(2);
    default:
      return String(value);
  }
}

function unavailableMessage(group: "face" | "hands", status: VisualMetric["status"]): string {
  if (group === "hands") {
    if (status === "disabled_by_tier") {
      return "Hand tracking was turned off for this session because your device couldn't keep up, so gesture metrics aren't available.";
    }
    if (status === "not_measured") {
      return "There wasn't enough usable video to measure your gestures for this session.";
    }
    return "Gestures could not be assessed because your hands were out of frame for most of the speech. Sit a little further back next time.";
  }

  if (status === "not_measured") {
    return "There wasn't enough usable video to measure camera-facing and head position for this session.";
  }
  return "Your face wasn't visible enough of the time to measure camera-facing and head position. Try sitting a little closer or improving the lighting next time.";
}

export default function VisualDeliverySection({
  report,
}: {
  report: SessionReport;
}): ReactElement | null {
  const status = report.video_analysis_status;

  if (status === "not_requested") return null;

  if (status === "awaiting_upload" || status === "received" || status === "processing") {
    return (
      <section style={{ marginBottom: "2.5rem" }}>
        <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
          Visual delivery
        </h2>
        <p className="alert alert-quiet">Visual analysis in progress.</p>
      </section>
    );
  }

  if (status === "unavailable") {
    return (
      <section style={{ marginBottom: "2.5rem" }}>
        <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
          Visual delivery
        </h2>
        <p className="alert alert-quiet">
          {report.video_unavailable_reason
            ? (VIDEO_UNAVAILABLE_REASON_LABEL[report.video_unavailable_reason] ??
              "Visual analysis wasn't available for this session.")
            : "Visual analysis wasn't available for this session."}{" "}
          Turn on visual feedback before your next recording to see it here.
        </p>
      </section>
    );
  }

  if (status === "failed" || status === "insufficient_data") {
    return (
      <section style={{ marginBottom: "2.5rem" }}>
        <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>
          Visual delivery
        </h2>
        <p className="alert alert-quiet">
          {status === "failed"
            ? "Visual analysis couldn't be completed for this session. Your speech feedback is unaffected."
            : "There wasn't enough usable video from this session to measure delivery. Your speech feedback is unaffected."}
        </p>
      </section>
    );
  }

  // status is "processed" or "partial" from here on.
  const analysis = report.video_analysis;
  if (!analysis) return null;

  const inRoom = analysis.quality.context.setting === "in_room_practice";
  const metrics = analysis.metrics;

  const rows = VISUAL_METRIC_ORDER.filter((key) => {
    if (inRoom && CAMERA_FACING_METRIC_KEYS.has(key)) return false;
    return key in metrics;
  });

  const faceBlocked = rows.find((key) => FACE_GATED_KEYS.has(key) && metrics[key].status !== "ok");
  const handsBlocked = rows.find((key) => HAND_GATED_KEYS.has(key) && metrics[key].status !== "ok");

  const okRows = rows.filter((key) => metrics[key].status === "ok");

  const sessionLevelFeedback = (report.visual_feedback?.visual_feedback ?? []).filter(
    (item) => !item.moment_id,
  );

  return (
    <section style={{ marginBottom: "2.5rem" }}>
      <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>
        Visual delivery
      </h2>

      <dl className="defs" style={{ marginBottom: "1.25rem" }}>
        {okRows.map((key) => {
          const metric = metrics[key];
          const info = VISUAL_METRIC_INFO[key];
          if (!info || metric.value === null) return null;

          return (
            <div key={key}>
              <dt>{info.label}</dt>
              <dd>
                <span style={{ fontWeight: 600, color: "var(--ink)" }}>
                  {formatValue(metric.value, info.format)}
                </span>
                {metric.confidence && (
                  <span
                    className="state"
                    data-tone={metric.confidence === "high" ? "done" : undefined}
                    style={{ marginLeft: "0.625rem" }}
                  >
                    {CONFIDENCE_LABEL[metric.confidence]}
                  </span>
                )}
                <p style={{ margin: "0.25rem 0 0" }}>{info.definition}</p>
              </dd>
            </div>
          );
        })}
      </dl>

      {faceBlocked && (
        <p className="note" style={{ marginBottom: "0.5rem" }}>
          {unavailableMessage("face", metrics[faceBlocked].status)}
        </p>
      )}
      {handsBlocked && (
        <p className="note" style={{ marginBottom: "0.5rem" }}>
          {unavailableMessage("hands", metrics[handsBlocked].status)}
        </p>
      )}

      {analysis.quality.warnings.length > 0 && (
        <ul style={{ margin: "0.75rem 0 0", padding: 0, listStyle: "none" }}>
          {analysis.quality.warnings.map((code) => (
            <li key={code} className="note">
              {VISUAL_WARNING_LABEL[code] ?? code}
            </li>
          ))}
        </ul>
      )}

      {report.visual_coaching_status === "failed" && (
        <p className="note" style={{ marginTop: "0.75rem" }}>
          Coaching notes for your visual delivery couldn&rsquo;t be generated
          for this session. The measurements above are unaffected.
        </p>
      )}

      {sessionLevelFeedback.length > 0 && (
        <ul className="findings" style={{ marginTop: "1.5rem" }}>
          {sessionLevelFeedback.map((item) => (
            <li
              className="finding"
              // "neutral" (e.g. a coverage note) intentionally gets no
              // data-severity, so .finding's default grey marker applies
              // instead of misrepresenting it as a criticism.
              data-severity={
                item.polarity === "strength"
                  ? "positive"
                  : item.polarity === "improve"
                    ? "medium"
                    : undefined
              }
              key={item.id}
            >
              <div>
                <p>{item.coaching}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
