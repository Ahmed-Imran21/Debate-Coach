"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import type { CSSProperties, FormEvent, ReactElement } from "react";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";
import {
  ApiError,
  getAccessToken,
  getProfile,
  redirectToLoginAfterSessionExpiry,
  updateProfile,
} from "@/lib/api";
import {
  BEST_LABEL,
  BIO_MAX,
  GOAL_OPTIONS,
  bioLength,
  browserTimeZone,
  fieldForMessage,
  formatRecorded,
  longestText,
  normalizeBio,
  normalizeUsername,
  sessionName,
  streakNote,
  validateBio,
  validateUsername,
  weekCaption,
  weekFill,
  weekText,
} from "@/lib/profile";
import type { Profile } from "@/lib/types";

const H2: CSSProperties = { fontSize: "var(--step-2)", marginBottom: "1rem" };
const FIELD_ERROR: CSSProperties = { color: "var(--brick)", margin: "0.375rem 0 0" };

// .field styles input and select only; the bio's textarea gets the
// same look from the same tokens.
const TEXTAREA: CSSProperties = {
  display: "block",
  width: "100%",
  font: "inherit",
  padding: "0.6875rem 0.75rem",
  border: "1px solid var(--rule-strong)",
  borderRadius: "var(--radius)",
  background: "var(--paper-raised)",
  color: "var(--ink)",
  resize: "vertical",
};

/**
 * The signed-in user's own profile: details, practice streak, weekly
 * goal and personal bests. Everything shown comes from GET
 * /v1/profile, which only ever returns the current user's data.
 */
export default function ProfilePage(): ReactElement {
  const router = useRouter();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // As on the practice page: a response landing after the user has
  // left must not redirect them from wherever they went.
  const leftPageRef = useRef(false);

  const handleAuth = useCallback(
    (caught: unknown): boolean => {
      if (caught instanceof ApiError && caught.status === 401) {
        if (!leftPageRef.current) redirectToLoginAfterSessionExpiry(router);
        return true;
      }
      return false;
    },
    [router],
  );

  useEffect(() => {
    leftPageRef.current = false;

    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }

    let cancelled = false;

    const load = async () => {
      try {
        let loaded = await getProfile();

        // Days and weeks follow the browser's time zone. Stored when
        // it's new or has changed (travel), and the figures come back
        // recomputed. Not being able to store it is not an error: the
        // backend keeps using what it had (UTC at first).
        const zone = browserTimeZone();
        if (zone && zone !== loaded.time_zone) {
          try {
            loaded = await updateProfile({ time_zone: zone });
          } catch (caught) {
            if (handleAuth(caught)) return;
          }
        }

        if (!cancelled) {
          setProfile(loaded);
          setLoadError(null);
        }
      } catch (caught) {
        if (cancelled || handleAuth(caught)) return;
        setLoadError("Could not load your profile. Reload the page to try again.");
      }
    };

    void load();

    return () => {
      cancelled = true;
      leftPageRef.current = true;
    };
  }, [router, handleAuth]);

  return (
    <div className="shell">
      <SiteHeader variant="app" />

      <main>
        {loadError && (
          <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
            <div className="wrap">
              <p className="alert alert-quiet" role="status">
                {loadError}
              </p>
            </div>
          </section>
        )}

        {!loadError && profile === null && (
          <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
            <div className="wrap">
              <p className="note">Loading.</p>
            </div>
          </section>
        )}

        {profile !== null && (
          <>
            <DetailsSection profile={profile} onSaved={setProfile} onAuthError={handleAuth} />
            <StreakSection profile={profile} />
            <GoalSection profile={profile} onSaved={setProfile} onAuthError={handleAuth} />
            <BestsSection profile={profile} />
          </>
        )}
      </main>

      <SiteFooter />
    </div>
  );
}

/* ---------------------------------------------------------- */
/* 1. Profile details                                          */
/* ---------------------------------------------------------- */

function DetailsSection({
  profile,
  onSaved,
  onAuthError,
}: {
  profile: Profile;
  onSaved: (profile: Profile) => void;
  onAuthError: (caught: unknown) => boolean;
}): ReactElement {
  const [editing, setEditing] = useState(false);
  const [username, setUsername] = useState("");
  const [bio, setBio] = useState("");
  const [errors, setErrors] = useState<{ username?: string; bio?: string }>({});
  const [formError, setFormError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const fullName = `${profile.first_name} ${profile.last_name}`.trim();

  function startEditing(): void {
    setUsername(profile.username ?? "");
    setBio(profile.bio ?? "");
    setErrors({});
    setFormError(null);
    setEditing(true);
  }

  async function save(event: FormEvent): Promise<void> {
    event.preventDefault();

    const found = {
      username: validateUsername(username) ?? undefined,
      bio: validateBio(bio) ?? undefined,
    };
    setErrors(found);
    setFormError(null);
    if (found.username || found.bio) return;

    setSaving(true);
    try {
      const saved = await updateProfile({
        username: normalizeUsername(username),
        bio: normalizeBio(bio),
      });
      onSaved(saved);
      setEditing(false);
    } catch (caught) {
      if (onAuthError(caught)) return;
      const message = caught instanceof ApiError ? caught.message : "Could not save your profile. Try again.";
      const field = fieldForMessage(message);
      if (field) setErrors({ [field]: message });
      else setFormError(message);
    } finally {
      setSaving(false);
    }
  }

  const typed = bioLength(bio);

  return (
    <section className="block-tight" style={{ paddingTop: "2.5rem" }}>
      <div className="wrap">
        <h1 style={{ fontSize: "var(--step-4)", overflowWrap: "anywhere" }}>{fullName}</h1>
        {profile.username && (
          <p className="lede" style={{ margin: "0.25rem 0 0" }}>
            @{profile.username}
          </p>
        )}

        {!editing && (
          <>
            {profile.bio ? (
              <p style={{ whiteSpace: "pre-line", overflowWrap: "anywhere", maxWidth: "52ch", margin: "1rem 0 0" }}>
                {profile.bio}
              </p>
            ) : (
              !profile.username && (
                <p className="note" style={{ margin: "1rem 0 0" }}>
                  Add a username and a short bio. Only you can see them.
                </p>
              )
            )}
            <div className="btn-row" style={{ marginTop: "1.25rem" }}>
              <button className="btn btn-quiet btn-sm" type="button" onClick={startEditing}>
                Edit profile
              </button>
            </div>
          </>
        )}

        {editing && (
          <form className="form-panel" style={{ maxWidth: "34rem", marginTop: "1.5rem" }} onSubmit={save} noValidate>
            {formError && (
              <p className="alert" role="alert">
                {formError}
              </p>
            )}

            <div className="field">
              <span>
                <label htmlFor="profile-username">Username (optional)</label>
              </span>
              <input
                id="profile-username"
                type="text"
                name="username"
                autoComplete="off"
                autoCapitalize="none"
                spellCheck={false}
                value={username}
                aria-invalid={errors.username ? true : undefined}
                aria-describedby="username-help"
                onChange={(event) => setUsername(event.target.value.toLowerCase())}
              />
              <p id="username-help" className="note" style={{ margin: "0.375rem 0 0" }}>
                3 to 20 characters: lowercase letters, numbers and underscores.
              </p>
              {errors.username && (
                <p className="note" role="alert" style={FIELD_ERROR}>
                  {errors.username}
                </p>
              )}
            </div>

            <div className="field">
              <span>
                <label htmlFor="profile-bio">Bio (optional)</label>
              </span>
              <textarea
                id="profile-bio"
                name="bio"
                rows={4}
                style={TEXTAREA}
                value={bio}
                aria-invalid={errors.bio ? true : undefined}
                aria-describedby="bio-count"
                onChange={(event) => setBio(event.target.value)}
              />
              <p
                id="bio-count"
                className="note"
                aria-live="polite"
                style={{ margin: "0.375rem 0 0", color: typed > BIO_MAX ? "var(--brick)" : undefined }}
              >
                {typed} / {BIO_MAX} characters
              </p>
              {errors.bio && (
                <p className="note" role="alert" style={FIELD_ERROR}>
                  {errors.bio}
                </p>
              )}
            </div>

            <p className="note" style={{ margin: "0 0 1.125rem" }}>
              Only you can see your username and bio. They never appear on shared reports.
            </p>

            <div className="btn-row">
              <button className="btn" type="submit" disabled={saving}>
                {saving ? "Saving" : "Save"}
              </button>
              <button className="btn btn-quiet" type="button" disabled={saving} onClick={() => setEditing(false)}>
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------- */
/* 2. Practice streak                                          */
/* ---------------------------------------------------------- */

function StreakSection({ profile }: { profile: Profile }): ReactElement {
  const { streak } = profile;
  const note = streakNote(streak);

  return (
    <section className="block-tight">
      <div className="wrap">
        <h2 style={H2}>Practice streak</h2>
        <div className="figures" style={{ maxWidth: "17rem" }}>
          <div className="figure">
            <b style={{ fontSize: "var(--step-5)" }}>{streak.current}</b>
            <span>day streak</span>
          </div>
        </div>
        <p className="note" style={{ margin: "0.75rem 0 0" }}>
          {longestText(streak.longest)}
        </p>
        {note && <p style={{ margin: "0.5rem 0 0", color: "var(--pine-deep)" }}>{note}</p>}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------- */
/* 3. Weekly goal                                              */
/* ---------------------------------------------------------- */

function GoalSection({
  profile,
  onSaved,
  onAuthError,
}: {
  profile: Profile;
  onSaved: (profile: Profile) => void;
  onAuthError: (caught: unknown) => boolean;
}): ReactElement {
  const [saving, setSaving] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { week } = profile;
  const caption = weekCaption(week);

  async function choose(goal: number): Promise<void> {
    if (goal === profile.weekly_goal || saving !== null) return;
    setSaving(goal);
    setError(null);
    try {
      onSaved(await updateProfile({ weekly_goal: goal }));
    } catch (caught) {
      if (onAuthError(caught)) return;
      setError(caught instanceof ApiError ? caught.message : "Could not save your goal. Try again.");
    } finally {
      setSaving(null);
    }
  }

  const pressed = saving ?? profile.weekly_goal;

  return (
    <section className="block-tight">
      <div className="wrap">
        <h2 style={H2}>Weekly goal</h2>

        <div style={{ maxWidth: "34rem" }}>
          <p style={{ margin: "0 0 0.5rem", fontSize: "var(--step-1)" }}>{weekText(week)}</p>
          <div
            className="bar-track"
            role="progressbar"
            aria-label="Sessions completed this week"
            aria-valuemin={0}
            aria-valuemax={week.goal}
            aria-valuenow={Math.min(week.completed, week.goal)}
          >
            <div className="bar-fill" style={{ width: `${weekFill(week)}%` }} />
          </div>
          {caption && (
            <p style={{ margin: "0.5rem 0 0", color: "var(--pine-deep)", fontWeight: 500 }}>{caption}</p>
          )}
          <p className="note" style={{ margin: "0.5rem 0 1.25rem" }}>
            Completed sessions from Monday to Sunday.
          </p>
        </div>

        <p style={{ fontSize: "0.875rem", fontWeight: 500, margin: "0 0 0.375rem" }} id="goal-label">
          Sessions per week
        </p>
        <div className="filters" role="group" aria-labelledby="goal-label">
          {GOAL_OPTIONS.map((goal) => (
            <button
              key={goal}
              className="filter"
              type="button"
              aria-pressed={pressed === goal}
              disabled={saving !== null}
              onClick={() => void choose(goal)}
            >
              {goal}
            </button>
          ))}
        </div>
        {error && (
          <p className="note" role="alert" style={FIELD_ERROR}>
            {error}
          </p>
        )}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------- */
/* 4. Personal bests                                           */
/* ---------------------------------------------------------- */

function BestsSection({ profile }: { profile: Profile }): ReactElement {
  return (
    <section className="block-tight" style={{ paddingBottom: "4rem" }}>
      <div className="wrap">
        <h2 style={H2}>Personal bests</h2>

        {profile.completed_sessions === 0 ? (
          <p className="note" style={{ maxWidth: "48ch" }}>
            No completed sessions yet. <Link href="/practice">Record your first speech</Link> and
            your best scores will appear here.
          </p>
        ) : (
          <ul className="rows" style={{ maxWidth: "46rem" }}>
            {profile.personal_bests.map((best) => {
              const label = BEST_LABEL[best.category];

              if (best.score === null || best.session_id === null || best.created_at === null) {
                return (
                  <li className="row" key={best.category}>
                    <div>
                      <div className="row-title">{label}</div>
                      <div className="row-meta">No score yet</div>
                    </div>
                  </li>
                );
              }

              return (
                <li className="row" key={best.category}>
                  <Link href={`/practice/${best.session_id}`}>
                    <div style={{ minWidth: 0 }}>
                      <div className="row-title">{label}</div>
                      <div className="row-meta" style={{ overflowWrap: "anywhere" }}>
                        {sessionName(best.title, best.created_at)} · {formatRecorded(best.created_at)}
                      </div>
                    </div>
                    <span className="row-score">{Math.round(best.score)}</span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}
