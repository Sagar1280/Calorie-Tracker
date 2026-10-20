import {
  useEffect,
  useMemo,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { ApiError, getProfile, logout, saveProfile } from "@/shared/api";
import {
  ACTIVITY_OPTIONS,
  SEX_OPTIONS,
  type ActivityLevel,
  type Profile,
  type ProfileInput,
  type Sex,
  type User,
} from "@/shared/types";
import { Topbar } from "@/shared/ui";
import { summarizeBmi } from "./bmi";

interface FormState {
  name: string;
  age: string;
  sex: Sex;
  heightCm: string;
  weightKg: string;
  activityLevel: ActivityLevel;
}

const EMPTY_FORM: FormState = {
  name: "",
  age: "",
  sex: "male",
  heightCm: "",
  weightKg: "",
  activityLevel: "moderate",
};

const ZONES = [
  { category: "Underweight", label: "Under", range: "< 18.5" },
  { category: "Healthy", label: "Healthy", range: "18.5–24.9" },
  { category: "Overweight", label: "Over", range: "25–29.9" },
  { category: "Obese", label: "Obese", range: "30+" },
] as const;

function formFromProfile(profile: Profile): FormState {
  return {
    name: profile.name,
    age: String(profile.age),
    sex: profile.sex,
    heightCm: String(profile.height_cm),
    weightKg: String(profile.weight_kg),
    activityLevel: profile.activity_level,
  };
}

interface ProfileScreenProps {
  user: User;
  nav?: ReactNode;
  onSessionExpired: () => void;
  onSignedOut: () => void;
}

export default function ProfileScreen({
  user,
  nav,
  onSessionExpired,
  onSignedOut,
}: ProfileScreenProps) {
  const [profile, setProfile] = useState<Profile | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    setLoadError(null);

    getProfile()
      .then(({ profile: loaded }) => {
        if (cancelled) return;
        setProfile(loaded);
        setForm(loaded ? formFromProfile(loaded) : EMPTY_FORM);
        setDirty(false);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          onSessionExpired();
          return;
        }
        setLoadError(
          "Could not reach the profile service. Make sure the API is running, then try again.",
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [reloadKey, onSessionExpired]);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 2600);
    return () => window.clearTimeout(timer);
  }, [notice]);

  const summary = useMemo(
    () => summarizeBmi(Number(form.weightKg), Number(form.heightCm)),
    [form.weightKg, form.heightCm],
  );

  const tone = summary?.tone ?? "neutral";

  const topbarRight = (
    <div className="topbar-actions">
      <span className="user-chip" title={`@${user.username}`}>
        @{user.username}
      </span>
      <button
        type="button"
        className="signout-button"
        onClick={handleSignOut}
        disabled={signingOut}
      >
        {signingOut ? "Signing out…" : "Sign out"}
      </button>
    </div>
  );

  function updateField<K extends keyof FormState>(
    key: K,
    value: FormState[K],
  ) {
    setForm((current) => ({ ...current, [key]: value }) as FormState);
    setDirty(true);
    if (error) setError(null);
  }

  function resetForm() {
    setForm(profile ? formFromProfile(profile) : EMPTY_FORM);
    setDirty(false);
    setError(null);
  }

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await logout();
      onSignedOut();
    } catch {
      setSigningOut(false);
      setError("Could not sign out. Check your connection and try again.");
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const name = form.name.trim();
    const age = Number(form.age);
    const height = Number(form.heightCm);
    const weight = Number(form.weightKg);

    if (!name) {
      setError("Add a name to create your profile.");
      return;
    }

    if (!Number.isInteger(age) || age < 2 || age > 120) {
      setError("Age must be a whole number between 2 and 120.");
      return;
    }

    if (!Number.isFinite(height) || height <= 50 || height > 260) {
      setError("Height must be between 50 and 260 cm.");
      return;
    }

    if (!Number.isFinite(weight) || weight < 10 || weight > 500) {
      setError("Weight must be between 10 and 500 kg.");
      return;
    }

    if (!summary) {
      setError("Enter a valid height and weight so we can calculate your BMI.");
      return;
    }

    const payload: ProfileInput = {
      name,
      age,
      sex: form.sex,
      height_cm: height,
      weight_kg: weight,
      activity_level: form.activityLevel,
      version: profile?.version ?? 0,
    };

    setSaving(true);

    try {
      const saved = await saveProfile(payload);
      setProfile(saved);
      setForm(formFromProfile(saved));
      setDirty(false);
      setNotice("Profile saved");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      if (caught instanceof ApiError && caught.status === 409) {
        if (caught.current) {
          setProfile(caught.current);
          setForm(formFromProfile(caught.current));
          setDirty(false);
          setError(
            "This profile was updated elsewhere. We loaded the latest version — review it and save again.",
          );
        } else {
          setError(
            "This profile changed elsewhere. Reload the page to get the latest version.",
          );
        }
      } else if (caught instanceof ApiError && caught.status === 422) {
        setError(
          "Some details are out of range. Check your age, height, and weight.",
        );
      } else if (caught instanceof ApiError) {
        setError(caught.message);
      } else {
        setError(
          "Could not reach the server. Check that the API is running and try again.",
        );
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="app tone-neutral">
        <Topbar center={nav} right={topbarRight} />
        <main className="page">
          <div className="skeleton skeleton-intro" />
          <section className="card skeleton-card" aria-label="Loading profile">
            <div className="skeleton skeleton-line skeleton-short" />
            <div className="skeleton skeleton-bmi" />
            <div className="skeleton skeleton-line" />
            <div className="skeleton skeleton-line skeleton-medium" />
          </section>
          <section className="card skeleton-card">
            <div className="skeleton skeleton-line skeleton-short" />
            <div className="skeleton skeleton-input" />
            <div className="skeleton skeleton-input" />
            <div className="skeleton skeleton-input" />
          </section>
          <p className="loading-caption">Loading your profile…</p>
        </main>
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="app tone-neutral">
        <Topbar center={nav} right={topbarRight} />
        <main className="page">
          <section className="card state-card">
            <span className="state-icon" aria-hidden="true">
              !
            </span>
            <h1>Can't reach the API</h1>
            <p>{loadError}</p>
            <button
              type="button"
              className="primary-button"
              onClick={() => setReloadKey((value) => value + 1)}
            >
              Try again
            </button>
          </section>
        </main>
      </div>
    );
  }

  const saveLabel = saving
    ? "Saving…"
    : profile
      ? dirty
        ? "Save changes"
        : "Saved"
      : "Create profile";

  return (
    <div className={`app tone-${tone}`}>
      <Topbar center={nav} right={topbarRight} />

      <main className="page">
        <section className="intro">
          <p className="eyebrow">Your baseline</p>
          <h1>Profile</h1>
          <p className="lede">
            Set your body details once. We use them to calculate BMI and, soon,
            calorie targets that fit you.
          </p>
        </section>

        {error && (
          <div className="banner" role="alert">
            <span className="banner-icon" aria-hidden="true">
              !
            </span>
            <p>{error}</p>
            <button
              type="button"
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError(null)}
            >
              ×
            </button>
          </div>
        )}

        <section
          className="bmi-card"
          aria-live="polite"
          aria-label={
            summary
              ? `BMI ${summary.bmi.toFixed(1)}, ${summary.category}`
              : "BMI not calculated yet"
          }
        >
          <div className="bmi-top">
            <div>
              <p className="eyebrow">Body mass index</p>
              <div className="bmi-number-row">
                <span className="bmi-number">
                  {summary ? summary.bmi.toFixed(1) : "—"}
                </span>
                <span className="bmi-unit">kg/m²</span>
              </div>
            </div>
            <span className={`status-chip ${summary ? "is-live" : ""}`}>
              <span className="status-dot" aria-hidden="true" />
              {summary ? summary.category : "Add details"}
            </span>
          </div>

          <p className="bmi-headline">
            {summary ? summary.headline : "Your range appears here"}
          </p>

          <div className={`scale ${summary ? "" : "scale-empty"}`}>
            <div className="scale-bar" aria-hidden="true">
              <span className="seg-under" />
              <span className="seg-healthy" />
              <span className="seg-over" />
              <span className="seg-obese" />
            </div>
            {summary && (
              <span
                className="scale-marker"
                style={{ left: `${summary.position}%` }}
                aria-hidden="true"
              />
            )}
          </div>

          <div className="zone-grid">
            {ZONES.map((zone) => (
              <div
                key={zone.category}
                className={`zone ${
                  summary?.category === zone.category ? "zone-active" : ""
                }`}
              >
                <span
                  className={`zone-dot zone-dot-${zone.category.toLowerCase()}`}
                  aria-hidden="true"
                />
                <span className="zone-label">{zone.label}</span>
                <span className="zone-range">{zone.range}</span>
              </div>
            ))}
          </div>

          {summary ? (
            <>
              <p className="bmi-detail">{summary.detail}</p>
              <div className="range-row">
                <span>Healthy weight at {form.heightCm || "—"} cm</span>
                <strong>
                  {summary.healthyMin.toFixed(1)}–{summary.healthyMax.toFixed(1)}{" "}
                  kg
                </strong>
              </div>
            </>
          ) : (
            <p className="bmi-detail muted">
              Enter a valid height and weight to calculate your BMI.
            </p>
          )}
        </section>

        <form className="profile-form" onSubmit={handleSubmit} noValidate>
          <section className="card form-card">
            <div className="section-head">
              <div>
                <h2>About you</h2>
                <p>Used for your BMI and future calorie goals.</p>
              </div>
              {dirty && (
                <button
                  type="button"
                  className="text-button"
                  onClick={resetForm}
                  disabled={saving}
                >
                  Reset
                </button>
              )}
            </div>

            <fieldset className="form-fields" disabled={saving}>
              <legend className="sr-only">Profile details</legend>

              <label className="field">
                <span className="field-label">Name</span>
                <input
                  className="text-input"
                  type="text"
                  name="name"
                  autoComplete="name"
                  maxLength={80}
                  placeholder="Your name"
                  value={form.name}
                  onChange={(event) =>
                    updateField("name", event.target.value)
                  }
                />
              </label>

              <div className="field-row">
                <label className="field">
                  <span className="field-label">Age</span>
                  <div className="input-shell">
                    <input
                      type="number"
                      name="age"
                      inputMode="numeric"
                      min={2}
                      max={120}
                      step={1}
                      placeholder="28"
                      value={form.age}
                      onChange={(event) => updateField("age", event.target.value)}
                    />
                    <span className="unit">yrs</span>
                  </div>
                </label>

                <div className="field">
                  <span className="field-label" id="sex-label">
                    Sex
                  </span>
                  <div
                    className="segmented"
                    role="group"
                    aria-labelledby="sex-label"
                  >
                    {SEX_OPTIONS.map((option) => (
                      <button
                        key={option.value}
                        type="button"
                        className={
                          form.sex === option.value ? "segment-active" : ""
                        }
                        aria-pressed={form.sex === option.value}
                        onClick={() => updateField("sex", option.value)}
                      >
                        {option.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="field-row even">
                <label className="field">
                  <span className="field-label">Height</span>
                  <div className="input-shell">
                    <input
                      type="number"
                      name="height"
                      inputMode="decimal"
                      min={50.1}
                      max={260}
                      step={0.1}
                      placeholder="175"
                      value={form.heightCm}
                      onChange={(event) =>
                        updateField("heightCm", event.target.value)
                      }
                    />
                    <span className="unit">cm</span>
                  </div>
                </label>

                <label className="field">
                  <span className="field-label">Weight</span>
                  <div className="input-shell">
                    <input
                      type="number"
                      name="weight"
                      inputMode="decimal"
                      min={10}
                      max={500}
                      step={0.1}
                      placeholder="72.5"
                      value={form.weightKg}
                      onChange={(event) =>
                        updateField("weightKg", event.target.value)
                      }
                    />
                    <span className="unit">kg</span>
                  </div>
                </label>
              </div>

              <label className="field">
                <span className="field-label">Activity level</span>
                <div className="select-wrap">
                  <select
                    name="activity"
                    value={form.activityLevel}
                    onChange={(event) =>
                      updateField(
                        "activityLevel",
                        event.target.value as ActivityLevel,
                      )
                    }
                  >
                    {ACTIVITY_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
              </label>
            </fieldset>
          </section>

          <p className="disclaimer">
            BMI is a screening tool, not a diagnosis. Talk to a clinician for
            advice that's personal to you.
          </p>

          <div className="save-dock">
            <div className="save-meta">
              <span
                className={`save-state ${dirty ? "is-dirty" : ""}`}
                aria-hidden="true"
              />
              {dirty
                ? "Unsaved changes"
                : profile
                  ? "All changes saved"
                  : "Nothing saved yet"}
            </div>
            <button
              type="submit"
              className="save-button"
              disabled={saving || !dirty}
            >
              {saveLabel}
            </button>
          </div>
        </form>
      </main>

      {notice && (
        <div className="toast" role="status">
          <span className="toast-check" aria-hidden="true">
            ✓
          </span>
          {notice}
        </div>
      )}
    </div>
  );
}
