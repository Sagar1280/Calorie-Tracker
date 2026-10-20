import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  getFood,
  listFoodReviews,
  listReviewFoods,
  logout,
  updateReviewFood,
} from "@/shared/api";
import type {
  AdminFoodReview,
  FoodDetail,
  FoodStatus,
  FoodSummary,
  FoodUnit,
  User,
} from "@/shared/types";
import { Topbar } from "@/shared/ui";

type ReviewSource = "all" | "off" | "curated";

interface AdminReviewScreenProps {
  user: User;
  nav: ReactNode;
  onSessionExpired: () => void;
  onSignedOut: () => void;
}

interface ReviewForm {
  name: string;
  brandName: string;
  category: string;
  subcategory: string;
  description: string;
  status: FoodStatus;
  isVerified: boolean;
  kcal: string;
  proteinG: string;
  carbsG: string;
  fatG: string;
  baseAmount: string;
  baseUnit: FoodUnit;
}

function toForm(detail: FoodDetail): ReviewForm {
  const variant = detail.default_variant ?? detail.variants[0] ?? null;
  return {
    name: detail.name,
    brandName: detail.brand?.name ?? "",
    category: detail.category,
    subcategory: detail.subcategory ?? "",
    description: detail.description ?? "",
    status: detail.status as FoodStatus,
    isVerified: detail.is_verified,
    kcal: variant ? String(variant.kcal) : "",
    proteinG: variant ? String(variant.protein_g) : "",
    carbsG: variant ? String(variant.carbs_g) : "",
    fatG: variant ? String(variant.fat_g) : "",
    baseAmount: variant ? String(variant.base_amount) : "100",
    baseUnit: variant?.base_unit ?? "g",
  };
}

function parseNumber(value: string): number {
  const number = Number(value);
  return Number.isFinite(number) ? number : Number.NaN;
}

export default function AdminReviewScreen({
  user,
  nav,
  onSessionExpired,
  onSignedOut,
}: AdminReviewScreenProps) {
  const [foods, setFoods] = useState<FoodSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState("");
  const [source, setSource] = useState<ReviewSource>("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<FoodDetail | null>(null);
  const [form, setForm] = useState<ReviewForm | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [history, setHistory] = useState<AdminFoodReview[]>([]);
  const [signingOut, setSigningOut] = useState(false);
  const [signOutError, setSignOutError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setListError(null);

    const timer = window.setTimeout(() => {
      listReviewFoods({
        q: query.trim() || undefined,
        source,
        limit: 100,
      })
        .then((list) => {
          if (cancelled) return;
          setFoods(list.items);
          setTotal(list.total);
        })
        .catch((caught) => {
          if (cancelled) return;
          if (caught instanceof ApiError && caught.status === 401) {
            onSessionExpired();
            return;
          }
          setListError(
            caught instanceof ApiError
              ? caught.message
              : "Could not load the review queue.",
          );
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, source, reloadKey, onSessionExpired]);

  async function selectFood(food: FoodSummary) {
    setSelectedId(food.id);
    setDetail(null);
    setForm(null);
    setHistory([]);
    setReviewNote("");
    setDetailLoading(true);
    setError(null);
    setNotice(null);

    try {
      const [loaded, reviews] = await Promise.all([
        getFood(food.id),
        listFoodReviews(food.id).catch(() => []),
      ]);
      setDetail(loaded);
      setForm(toForm(loaded));
      setHistory(reviews);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not load that food.",
      );
    } finally {
      setDetailLoading(false);
    }
  }

  function setField<K extends keyof ReviewForm>(
    key: K,
    value: ReviewForm[K],
  ) {
    setForm((current) =>
      current ? { ...current, [key]: value } : current,
    );
  }

  async function handleSave(
    event?: FormEvent<HTMLFormElement>,
    overrides?: Partial<ReviewForm>,
  ) {
    event?.preventDefault();
    if (!detail || !form) return;

    const values = { ...form, ...overrides };
    const kcal = parseNumber(values.kcal);
    const proteinG = parseNumber(values.proteinG);
    const carbsG = parseNumber(values.carbsG);
    const fatG = parseNumber(values.fatG);
    const baseAmount = parseNumber(values.baseAmount);

    if (!values.name.trim() || !values.category.trim()) {
      setError("Name and category are required.");
      return;
    }
    if (!Number.isFinite(kcal) || kcal < 0 || kcal > 10000) {
      setError("Calories must be between 0 and 10,000.");
      return;
    }
    if (
      !Number.isFinite(proteinG) ||
      !Number.isFinite(carbsG) ||
      !Number.isFinite(fatG) ||
      proteinG < 0 ||
      carbsG < 0 ||
      fatG < 0
    ) {
      setError("Macros must be zero or greater.");
      return;
    }
    if (!Number.isFinite(baseAmount) || baseAmount <= 0) {
      setError("Base amount must be greater than zero.");
      return;
    }

    setSaving(true);
    setError(null);
    setNotice(null);

    try {
      const updated = await updateReviewFood(detail.id, {
        name: values.name.trim(),
        category: values.category.trim(),
        subcategory: values.subcategory.trim() || null,
        brand_name: values.brandName.trim() || null,
        description: values.description.trim() || null,
        status: values.status,
        is_verified: values.isVerified,
        review_note: reviewNote.trim() || null,
        variant: {
          kcal: Math.round(kcal),
          protein_g: proteinG,
          carbs_g: carbsG,
          fat_g: fatG,
          base_amount: baseAmount,
          base_unit: values.baseUnit,
        },
      });
      setDetail(updated);
      setForm(toForm(updated));
      setReviewNote("");
      setHistory(await listFoodReviews(updated.id).catch(() => []));
      setNotice(
        updated.is_verified && updated.status === "approved"
          ? "Saved and verified. This item has left the review queue."
          : "Saved. The review queue has been updated.",
      );
      setReloadKey((value) => value + 1);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not save those changes.",
      );
    } finally {
      setSaving(false);
    }
  }

  async function handleSignOut() {
    setSigningOut(true);
    setSignOutError(null);
    try {
      await logout();
      onSignedOut();
    } catch {
      setSigningOut(false);
      setSignOutError("Could not sign out. Check your connection and try again.");
    }
  }

  const variant = detail?.default_variant ?? detail?.variants[0] ?? null;

  return (
    <div className="app">
      <Topbar
        center={nav}
        right={
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
              {signingOut ? "Signing out..." : "Sign out"}
            </button>
          </div>
        }
      />

      <main className="page review-page">
        <section className="card form-card review-intro">
          <div className="section-head">
            <div>
              <p className="eyebrow">Admin</p>
              <h1>Food review</h1>
              <p>
                Check Open Food Facts imports and curated drafts, correct
                their nutrition, and leave an audit note before verifying.
              </p>
            </div>
            <span className="review-count">{total} pending</span>
          </div>

          <div className="review-source-tabs" role="group" aria-label="Queue source">
            {(
              [
                ["all", "All drafts"],
                ["off", "Open Food Facts"],
                ["curated", "Curated"],
              ] as const
            ).map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={source === value ? "active" : ""}
                aria-pressed={source === value}
                onClick={() => {
                  setSource(value);
                  setSelectedId(null);
                  setDetail(null);
                  setForm(null);
                  setHistory([]);
                  setNotice(null);
                  setError(null);
                }}
              >
                {label}
              </button>
            ))}
          </div>

          <label className="field">
            <span className="field-label">Search review queue</span>
            <input
              className="text-input"
              type="search"
              name="review-search"
              autoComplete="off"
              placeholder="Search foods by name or alias"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>

          {notice && (
            <p className="review-notice" role="status">
              {notice}
            </p>
          )}
          {signOutError && <p className="form-error">{signOutError}</p>}
        </section>

        <div className="review-layout">
          <section className="card review-list-card" aria-label="Review queue">
            {loading ? (
              <p className="search-note">Loading review queue...</p>
            ) : listError ? (
              <p className="search-note error">{listError}</p>
            ) : foods.length === 0 ? (
              <div className="review-empty">
                <strong>No unverified foods in this view.</strong>
                <span>Imported and curated drafts will appear here.</span>
              </div>
            ) : (
              <div className="review-list">
                {foods.map((food) => (
                  <button
                    key={food.id}
                    type="button"
                    className={
                      selectedId === food.id
                        ? "review-item active"
                        : "review-item"
                    }
                    onClick={() => selectFood(food)}
                  >
                    <span className="review-item-main">
                      <strong>{food.name}</strong>
                      <span>
                        {[food.brand?.name, food.category]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </span>
                    <span className="review-item-side">
                      <span className="review-pill">Needs review</span>
                      <span>
                        {food.default_variant
                          ? `${food.default_variant.kcal} kcal`
                          : "No nutrition"}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
            )}
          </section>

          <section className="card review-editor" aria-live="polite">
            {detailLoading ? (
              <p className="search-note">Loading food details...</p>
            ) : !detail || !form || !variant ? (
              <div className="review-empty">
                <strong>Select a food to review.</strong>
                <span>
                  Check the name, brand, category, and nutrition values.
                </span>
              </div>
            ) : (
              <form className="review-form" onSubmit={handleSave}>
                <div className="section-head">
                  <div>
                    <p className="eyebrow">
                      {detail.source === "off"
                        ? "Imported from Open Food Facts"
                        : "Curated food draft"}
                    </p>
                    <h2>{detail.name}</h2>
                    <p>
                      Barcode{" "}
                      {detail.barcodes[0]?.barcode ?? "not recorded"}
                    </p>
                  </div>
                  <span className="review-pill">
                    {detail.status}
                    {detail.is_verified ? " · verified" : ""}
                  </span>
                </div>

                <label className="field">
                  <span className="field-label">Food name</span>
                  <input
                    className="text-input"
                    type="text"
                    maxLength={160}
                    value={form.name}
                    onChange={(event) =>
                      setField("name", event.target.value)
                    }
                  />
                </label>

                <div className="review-grid">
                  <label className="field">
                    <span className="field-label">Brand</span>
                    <input
                      className="text-input"
                      type="text"
                      maxLength={80}
                      value={form.brandName}
                      onChange={(event) =>
                        setField("brandName", event.target.value)
                      }
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Category</span>
                    <input
                      className="text-input"
                      type="text"
                      maxLength={32}
                      value={form.category}
                      onChange={(event) =>
                        setField("category", event.target.value)
                      }
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Subcategory</span>
                    <input
                      className="text-input"
                      type="text"
                      maxLength={48}
                      value={form.subcategory}
                      onChange={(event) =>
                        setField("subcategory", event.target.value)
                      }
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Status</span>
                    <div className="select-wrap">
                      <select
                        value={form.status}
                        onChange={(event) =>
                          setField(
                            "status",
                            event.target.value as FoodStatus,
                          )
                        }
                      >
                        <option value="approved">Approved</option>
                        <option value="pending">Pending</option>
                        <option value="rejected">Rejected</option>
                        <option value="private">Private</option>
                      </select>
                    </div>
                  </label>
                </div>

                <label className="field">
                  <span className="field-label">Description</span>
                  <textarea
                    className="textarea-input"
                    rows={3}
                    maxLength={2000}
                    value={form.description}
                    onChange={(event) =>
                      setField("description", event.target.value)
                    }
                  />
                </label>

                <div className="review-grid review-macros">
                  <label className="field">
                    <span className="field-label">Calories / 100</span>
                    <div className="input-shell">
                      <input
                        type="number"
                        min={0}
                        max={10000}
                        step={1}
                        value={form.kcal}
                        onChange={(event) =>
                          setField("kcal", event.target.value)
                        }
                      />
                      <span className="unit">kcal</span>
                    </div>
                  </label>

                  <label className="field">
                    <span className="field-label">Protein</span>
                    <div className="input-shell">
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={form.proteinG}
                        onChange={(event) =>
                          setField("proteinG", event.target.value)
                        }
                      />
                      <span className="unit">g</span>
                    </div>
                  </label>

                  <label className="field">
                    <span className="field-label">Carbs</span>
                    <div className="input-shell">
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={form.carbsG}
                        onChange={(event) =>
                          setField("carbsG", event.target.value)
                        }
                      />
                      <span className="unit">g</span>
                    </div>
                  </label>

                  <label className="field">
                    <span className="field-label">Fat</span>
                    <div className="input-shell">
                      <input
                        type="number"
                        min={0}
                        step={0.1}
                        value={form.fatG}
                        onChange={(event) =>
                          setField("fatG", event.target.value)
                        }
                      />
                      <span className="unit">g</span>
                    </div>
                  </label>
                </div>

                <div className="review-grid review-grid-narrow">
                  <label className="field">
                    <span className="field-label">Base amount</span>
                    <div className="input-shell">
                      <input
                        type="number"
                        min={1}
                        max={10000}
                        step={1}
                        value={form.baseAmount}
                        onChange={(event) =>
                          setField("baseAmount", event.target.value)
                        }
                      />
                      <span className="unit">{form.baseUnit}</span>
                    </div>
                  </label>

                  <label className="field">
                    <span className="field-label">Base unit</span>
                    <div className="select-wrap">
                      <select
                        value={form.baseUnit}
                        onChange={(event) =>
                          setField(
                            "baseUnit",
                            event.target.value as FoodUnit,
                          )
                        }
                      >
                        <option value="g">grams</option>
                        <option value="ml">millilitres</option>
                      </select>
                    </div>
                  </label>
                </div>

                <label className="field">
                  <span className="field-label">Review note</span>
                  <textarea
                    className="textarea-input"
                    rows={2}
                    maxLength={1000}
                    placeholder="What did you check or change?"
                    value={reviewNote}
                    onChange={(event) => setReviewNote(event.target.value)}
                  />
                </label>

                <label className="review-check">
                  <input
                    type="checkbox"
                    checked={form.isVerified}
                    onChange={(event) =>
                      setField("isVerified", event.target.checked)
                    }
                  />
                  <span>Mark nutrition as verified</span>
                </label>

                <div className="review-actions">
                  <button
                    type="submit"
                    className="save-button add-entry-button"
                    disabled={saving}
                  >
                    {saving ? "Saving..." : "Save changes"}
                  </button>
                  <button
                    type="button"
                    className="scan-button"
                    disabled={saving}
                    onClick={() =>
                      handleSave(undefined, {
                        status: "approved",
                        isVerified: true,
                      })
                    }
                  >
                    Approve and verify
                  </button>
                  <button
                    type="button"
                    className="text-button review-reject"
                    disabled={saving || form.status === "rejected"}
                    onClick={() =>
                      handleSave(undefined, {
                        status: "rejected",
                        isVerified: false,
                      })
                    }
                  >
                    Reject
                  </button>
                </div>

                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}

                <div className="review-history">
                  <div className="review-history-head">
                    <span className="field-label">Review history</span>
                    <span>{history.length} note{history.length === 1 ? "" : "s"}</span>
                  </div>
                  {history.length === 0 ? (
                    <p className="search-note">No reviews recorded yet.</p>
                  ) : (
                    history.map((item) => (
                      <div className="review-history-item" key={item.id}>
                        <div>
                          <strong>{item.action}</strong>
                          <span>
                            {item.reviewer_username
                              ? `@${item.reviewer_username}`
                              : "Unknown reviewer"}
                            {" ? "}
                            {new Date(item.created_at).toLocaleString("en-GB")}
                          </span>
                        </div>
                        <p>
                          {item.note ||
                            (item.action === "approved"
                              ? "Approved and verified."
                              : item.action === "rejected"
                                ? "Rejected."
                                : "Saved without a note.")}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </form>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}
