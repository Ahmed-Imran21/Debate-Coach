"use client";

import type { ReactElement } from "react";

import { NO_PROMPT, findMotion, toMotionId } from "@/lib/motions";
import type { Motion } from "@/lib/types";

/**
 * "Practice prompt" dropdown for the recorder. Defaults to No prompt;
 * once a motion is picked, its full wording shows underneath. The
 * notes are <small>, not <span>: `.field > span` is the label style.
 */
export default function MotionPicker({
  motions,
  value,
  onChange,
  disabled = false,
  loadFailed = false,
}: {
  motions: Motion[];
  value: string | null;
  onChange: (motionId: string | null) => void;
  disabled?: boolean;
  loadFailed?: boolean;
}): ReactElement {
  const chosen = findMotion(motions, value);

  return (
    <label className="field">
      <span>Practice prompt (optional)</span>
      <select
        value={value ?? NO_PROMPT}
        onChange={(event) => onChange(toMotionId(event.target.value))}
        disabled={disabled}
      >
        <option value={NO_PROMPT}>No prompt</option>
        {motions.map((m) => (
          <option key={m.id} value={m.id}>
            {m.title}
          </option>
        ))}
      </select>
      {chosen ? (
        <small className="note" style={{ display: "block", marginTop: "0.375rem" }}>
          {chosen.description} Your coaching will also judge how well you address it.
        </small>
      ) : (
        loadFailed && (
          <small className="note" style={{ display: "block", marginTop: "0.375rem" }}>
            Practice prompts could not be loaded. You can still record without one.
          </small>
        )
      )}
    </label>
  );
}
