import type { ReactElement } from "react";

import { formatClock } from "@/components/SpeechTrack";
import type { CorrelatedMoment, MomentObservation, SessionReport, VisualFeedbackItem } from "@/lib/types";

const UNIT_TYPE_LABEL: Record<string, string> = {
  claim: "Claim",
  rebuttal: "Rebuttal",
  conclusion: "Conclusion",
};

function describeObservation(obs: MomentObservation): string | null {
  if (obs.kind === "event" && obs.type === "gaze_away") {
    const direction = obs.direction ?? "away";
    return `Looked ${direction} for ${(obs.duration_s ?? 0).toFixed(1)}s`;
  }

  if (obs.metric === "camera_facing_ratio" && obs.unit_value != null) {
    const unit = Math.round(obs.unit_value * 100);
    const session = obs.session_value != null ? Math.round(obs.session_value * 100) : null;
    return session != null
      ? `Facing the camera ${unit}% of this part, versus ${session}% across the whole session`
      : `Facing the camera ${unit}% of this part`;
  }

  if (obs.metric === "head_down_fraction" && obs.unit_value != null) {
    return `Head down for ${Math.round(obs.unit_value * 100)}% of this part`;
  }

  if (obs.metric === "hands_still_fraction" && obs.unit_value != null) {
    return `Hands still for ${Math.round(obs.unit_value * 100)}% of this part`;
  }

  if (obs.metric === "hand_activity_ratio" && obs.unit_value != null) {
    return `Hand movement ${obs.unit_value.toFixed(1)}× your typical pace`;
  }

  return null;
}

function MomentBody({
  moment,
  coaching,
  onSeek,
}: {
  moment: CorrelatedMoment;
  coaching: string | null;
  onSeek: ((seconds: number) => void) | null;
}): ReactElement {
  const facts = moment.observations
    .map(describeObservation)
    .filter((text): text is string => Boolean(text));

  return (
    <div>
      <p className="finding-meta">
        {formatClock(moment.start)}–{formatClock(moment.end)}
        {moment.anchor.type && UNIT_TYPE_LABEL[moment.anchor.type]
          ? `. ${UNIT_TYPE_LABEL[moment.anchor.type]}`
          : ""}
        {onSeek && (
          <>
            {". "}
            <button
              type="button"
              className="filter"
              style={{ padding: "0.125rem 0.5rem", fontSize: "0.8125rem" }}
              onClick={() => onSeek(Math.max(0, moment.start - 1))}
            >
              Play from here
            </button>
          </>
        )}
      </p>

      {moment.excerpt_text && <blockquote>{moment.excerpt_text}</blockquote>}

      {facts.length > 0 && (
        <ul style={{ margin: "0.25rem 0 0.5rem", paddingLeft: "1.125rem", color: "var(--ink-soft)" }}>
          {facts.map((fact, index) => (
            <li key={index}>{fact}</li>
          ))}
        </ul>
      )}

      {coaching && <p className="rec">{coaching}</p>}
    </div>
  );
}

export default function KeyMomentsList({
  report,
  onSeek,
}: {
  report: SessionReport;
  onSeek?: (seconds: number) => void;
}): ReactElement | null {
  const moments = report.correlated_moments ?? [];
  if (moments.length === 0) return null;

  const momentsById = new Map(moments.map((m) => [m.id, m]));
  const feedbackItems = report.visual_feedback?.visual_feedback ?? [];
  const coachingByMomentId = new Map<string, VisualFeedbackItem>();
  for (const item of feedbackItems) {
    if (item.moment_id) coachingByMomentId.set(item.moment_id, item);
  }

  // Coaching succeeded: show only the moments the model actually
  // commented on. Coaching failed or produced nothing: fall back to
  // the moments themselves so the facts computed from the video are
  // still shown, per §8.4's "show metrics and moments without
  // coaching text" for a failed visual_coaching_status.
  const showRaw = report.visual_coaching_status !== "completed" || coachingByMomentId.size === 0;

  const entries: Array<{ moment: CorrelatedMoment; coaching: string | null; key: string }> = showRaw
    ? [...moments].sort((a, b) => b.salience - a.salience).map((moment) => ({ moment, coaching: null, key: moment.id }))
    : feedbackItems
        .filter((item) => item.moment_id && momentsById.has(item.moment_id))
        .map((item) => ({
          moment: momentsById.get(item.moment_id as string) as CorrelatedMoment,
          coaching: item.coaching,
          key: item.id,
        }));

  if (entries.length === 0) return null;

  return (
    <section style={{ marginBottom: "2.5rem" }}>
      <h2 style={{ fontSize: "var(--step-2)", marginBottom: "1rem" }}>
        Key moments
      </h2>

      <ul className="findings">
        {entries.map(({ moment, coaching, key }) => (
          <li
            className="finding"
            data-severity={moment.polarity === "strength" ? "positive" : "medium"}
            key={key}
          >
            <MomentBody moment={moment} coaching={coaching} onSeek={onSeek ?? null} />
          </li>
        ))}
      </ul>
    </section>
  );
}
