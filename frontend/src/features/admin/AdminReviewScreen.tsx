import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import {
  ApiError,
  bulkReviewFoods,
  createReviewFood,
  getFood,
  listFoodReviews,
  listReviewFoods,
  logout,
  updateReviewFood,
} from "@/shared/api";
import type {
  AdminBulkAction,
  AdminFoodReview,
  AdminFoodUpdateInput,
  FoodDetail,
  FoodStatus,
  FoodSummary,
  FoodUnit,
  User,
} from "@/shared/types";
import { Topbar } from "@/shared/ui";

type ReviewSource = "all" | "off" | "curated" | "user";
type ReviewScope = "pending" | "all";

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

interface ConfirmRequest {
  title: string;
  description: string;
  confirmLabel: string;
  danger?: boolean;
  run: (password: string) => Promise<void>;
}

const EMPTY_FORM: ReviewForm = {
  name: "",
  brandName: "",
  category: "dish",
  subcategory: "",
  description: "",
  status: "pending",
  isVerified: false,
  kcal: "",
  proteinG: "",
  carbsG: "",
  fatG: "",
  baseAmount: "100",
  baseUnit: "g",
};

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

function validateForm(values: ReviewForm): string | null {
  const kcal = parseNumber(values.kcal);
  const proteinG = parseNumber(values.proteinG);
  const carbsG = parseNumber(values.carbsG);
  const fatG = parseNumber(values.fatG);
  const baseAmount = parseNumber(values.baseAmount);

  if (!values.name.trim() || !values.category.trim()) {
    return "Name and category are required.";
  }
  if (!Number.isFinite(kcal) || kcal < 0 || kcal > 10000) {
    return "Calories must be between 0 and 10,000.";
  }
  if (
    !Number.isFinite(proteinG) ||
    !Number.isFinite(carbsG) ||
    !Number.isFinite(fatG) ||
    proteinG < 0 ||
    carbsG < 0 ||
    fatG < 0
  ) {
    return "Macros must be zero or greater.";
  }
  if (!Number.isFinite(baseAmount) || baseAmount <= 0) {
    return "Base amount must be greater than zero.";
  }
  return null;
}

function toInput(values: ReviewForm, note: string): AdminFoodUpdateInput {
  return {
    name: values.name.trim(),
    category: values.category.trim(),
    subcategory: values.subcategory.trim() || null,
    brand_name: values.brandName.trim() || null,
    description: values.description.trim() || null,
    status: values.status,
    is_verified: values.isVerified,
    review_note: note.trim() || null,
    variant: {
      kcal: Math.round(parseNumber(values.kcal)),
      protein_g: parseNumber(values.proteinG),
      carbs_g: parseNumber(values.carbsG),
      fat_g: parseNumber(values.fatG),
      base_amount: parseNumber(values.baseAmount),
      base_unit: values.baseUnit,
    },
  };
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
  const [scope, setScope] = useState<ReviewScope>("pending");
  const [source, setSource] = useState<ReviewSource>("all");
  const [reloadKey, setReloadKey] = useState(0);
  const [loading, setLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [detail, setDetail] = useState<FoodDetail | null>(null);
  const [form, setForm] = useState<ReviewForm | null>(null);
  const [createMode, setCreateMode] = useState(false);
  const [createForm, setCreateForm] = useState<ReviewForm>(EMPTY_FORM);
  const [detailLoading, setDetailLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reviewNote, setReviewNote] = useState("");
  const [history, setHistory] = useState<AdminFoodReview[]>([]);
  const [confirm, setConfirm] = useState<ConfirmRequest | null>(null);
  const [confirmPassword, setConfirmPassword] = useState("");
  const [confirmError, setConfirmError] = useState<string | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);
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
        status: scope === "pending" ? "pending" : undefined,
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
  }, [query, scope, source, reloadKey, onSessionExpired]);

  function clearEditor() {
    setDetail(null);
    setForm(null);
    setHistory([]);
    setReviewNote("");
    setError(null);
    setNotice(null);
    setCreateMode(false);
    setCreateForm(EMPTY_FORM);
  }

  async function selectFood(food: FoodSummary) {
    clearEditor();
    setSelectedId(food.id);
    setDetailLoading(true);

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

  function startCreate() {
    clearEditor();
    setSelectedId(null);
    setCreateMode(true);
    setCreateForm(EMPTY_FORM);
    setNotice(null);
  }

  function setField<K extends keyof ReviewForm>(
    key: K,
    value: ReviewForm[K],
  ) {
    if (createMode) {
      setCreateForm((current) => ({ ...current, [key]: value }));
      return;
    }
    setForm((current) =>
      current ? { ...current, [key]: value } : current,
    );
  }

  function toggleSelected(foodId: number) {
    setSelectedIds((current) =>
      current.includes(foodId)
        ? current.filter((id) => id !== foodId)
        : [...current, foodId],
    );
  }

  function toggleAll() {
    if (foods.length > 0 && foods.every((food) => selectedIds.includes(food.id))) {
      setSelectedIds([]);
      return;
    }
    setSelectedIds(foods.map((food) => food.id));
  }

  function openConfirm(request: ConfirmRequest) {
    setConfirm(request);
    setConfirmPassword("");
    setConfirmError(null);
  }

  function closeConfirm() {
    if (confirmBusy) return;
    setConfirm(null);
    setConfirmPassword("");
    setConfirmError(null);
  }

  async function runWithPassword(action: () => Promise<void>) {
    setConfirmBusy(true);
    setConfirmError(null);
    setSaving(true);
    setError(null);

    try {
      await action();
      setConfirm(null);
      setConfirmPassword("");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        setConfirm(null);
        onSessionExpired();
        return;
      }
      setConfirmError(
        caught instanceof ApiError
          ? caught.message
          : "That admin action could not be completed.",
      );
    } finally {
      setConfirmBusy(false);
      setSaving(false);
    }
  }

  function handleSave(
    event?: FormEvent<HTMLFormElement>,
    overrides?: Partial<ReviewForm>,
  ) {
    event?.preventDefault();
    const current = createMode ? createForm : form;
    if (!current) return;
    if (!createMode && !detail) return;

    const values = { ...current, ...overrides };
    const validationError = validateForm(values);
    if (validationError) {
      setError(validationError);
      return;
    }

    setError(null);
    setNotice(null);

    if (createMode) {
      openConfirm({
        title: "Create this food?",
        description:
          "Enter the admin confirmation password to add this food to the database.",
        confirmLabel: "Create food",
        run: async (password) => {
          await runWithPassword(async () => {
            const created = await createReviewFood(
              toInput(values, reviewNote),
              password,
            );
            setCreateMode(false);
            setCreateForm(EMPTY_FORM);
            setSelectedId(created.id);
            setDetail(created);
            setForm(toForm(created));
            setReviewNote("");
            setHistory(
              await listFoodReviews(created.id).catch(() => []),
            );
            if (created.status === "approved" && created.is_verified) {
              setScope("all");
            }
            setNotice("Food created. The review list has been refreshed.");
            setReloadKey((value) => value + 1);
          });
        },
      });
      return;
    }

    const food = detail;
    if (!food) return;
    openConfirm({
      title: "Save these changes?",
      description:
        "Enter the admin confirmation password to update this food in the database.",
      confirmLabel: "Save changes",
      run: async (password) => {
        await runWithPassword(async () => {
          const updated = await updateReviewFood(
            food.id,
            toInput(values, reviewNote),
            password,
          );
          setDetail(updated);
          setForm(toForm(updated));
          setReviewNote("");
          setHistory(await listFoodReviews(updated.id).catch(() => []));
          setNotice(
            updated.is_verified && updated.status === "approved"
              ? "Saved and verified. This item has left the review queue."
              : "Saved. The review list has been updated.",
          );
          setReloadKey((value) => value + 1);
        });
      },
    });
  }

  function requestBatch(action: AdminBulkAction) {
    if (selectedIds.length === 0) return;
    const count = selectedIds.length;
    const labels: Record<AdminBulkAction, string> = {
      approve: "Approve selected",
      reject: "Reject selected",
      delete: "Delete selected",
    };
    const descriptions: Record<AdminBulkAction, string> = {
      approve:
        "These foods will be approved and marked verified. Enter the admin confirmation password.",
      reject:
        "These foods will be rejected and marked unverified. Enter the admin confirmation password.",
      delete:
        "These foods will be permanently deleted. Enter the admin confirmation password.",
    };

    openConfirm({
      title: `${labels[action]} (${count})?`,
      description: descriptions[action],
      confirmLabel: labels[action],
      danger: action === "delete",
      run: async (password) => {
        await runWithPassword(async () => {
          const result = await bulkReviewFoods(
            { ids: selectedIds, action },
            password,
          );
          if (
            action === "delete" &&
            selectedId !== null &&
            selectedIds.includes(selectedId)
          ) {
            clearEditor();
            setSelectedId(null);
          }
          setSelectedIds([]);
          setNotice(
            `${result.affected} food${result.affected === 1 ? "" : "s"} ${
              action === "delete"
                ? "deleted"
                : action === "approve"
                  ? "approved"
                  : "rejected"
            }.`,
          );
          setReloadKey((value) => value + 1);
        });
      },
    });
  }

  async function handleConfirmSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!confirm) return;
    if (!confirmPassword) {
      setConfirmError("Enter the admin confirmation password.");
      return;
    }
    await confirm.run(confirmPassword);
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

  const activeForm = createMode ? createForm : form;
  const allSelected =
    foods.length > 0 && foods.every((food) => selectedIds.includes(food.id));

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
              <h1>Food database</h1>
              <p>
                Add foods, correct nutrition, approve batches, and keep the
                shared database growing. Every change requires the admin
                confirmation password.
              </p>
            </div>
            <div className="review-intro-actions">
              <span className="review-count">
                {total} {scope === "pending" ? "pending" : "foods"}
              </span>
              <button
                type="button"
                className="save-button review-add"
                onClick={startCreate}
              >
                Add food
              </button>
            </div>
          </div>

          <div className="review-filter-row">
            <div
              className="review-scope-tabs"
              role="group"
              aria-label="Food scope"
            >
              {(
                [
                  ["pending", "Needs review"],
                  ["all", "All foods"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={scope === value ? "active" : ""}
                  aria-pressed={scope === value}
                  onClick={() => {
                    setScope(value);
                    setSelectedIds([]);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>

            <div
              className="review-source-tabs"
              role="group"
              aria-label="Food source"
            >
              {(
                [
                  ["all", "All sources"],
                  ["off", "Open Food Facts"],
                  ["curated", "Curated"],
                  ["user", "Photo drafts"],
                ] as const
              ).map(([value, label]) => (
                <button
                  key={value}
                  type="button"
                  className={source === value ? "active" : ""}
                  aria-pressed={source === value}
                  onClick={() => {
                    setSource(value);
                    setSelectedIds([]);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          </div>

          <label className="field">
            <span className="field-label">Search foods</span>
            <input
              className="text-input"
              type="search"
              name="review-search"
              autoComplete="off"
              placeholder="Search by name or alias"
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
          <section className="card review-list-card" aria-label="Food list">
            {loading ? (
              <p className="search-note">Loading foods...</p>
            ) : listError ? (
              <p className="search-note error">{listError}</p>
            ) : foods.length === 0 ? (
              <div className="review-empty">
                <strong>No foods in this view.</strong>
                <span>Change the filters or add a new food.</span>
              </div>
            ) : (
              <>
                <div className="review-list-head">
                  <label className="review-select-all">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                    />
                    <span>Select all</span>
                  </label>
                  <span>{selectedIds.length} selected</span>
                </div>

                {selectedIds.length > 0 && (
                  <div className="review-batch-bar">
                    <button
                      type="button"
                      className="save-button"
                      onClick={() => requestBatch("approve")}
                    >
                      Approve
                    </button>
                    <button
                      type="button"
                      className="scan-button"
                      onClick={() => requestBatch("reject")}
                    >
                      Reject
                    </button>
                    <button
                      type="button"
                      className="text-button review-reject"
                      onClick={() => requestBatch("delete")}
                    >
                      Delete
                    </button>
                  </div>
                )}

                <div className="review-list">
                  {foods.map((food) => (
                    <div
                      key={food.id}
                      className={
                        selectedId === food.id
                          ? "review-row active"
                          : "review-row"
                      }
                    >
                      <input
                        className="review-select"
                        type="checkbox"
                        checked={selectedIds.includes(food.id)}
                        onChange={() => toggleSelected(food.id)}
                        aria-label={`Select ${food.name}`}
                      />
                      <button
                        type="button"
                        className="review-item"
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
                          <span className="review-pill">
                            {food.is_verified ? "Verified" : "Needs review"}
                          </span>
                          <span>
                            {food.default_variant
                              ? `${food.default_variant.kcal} kcal`
                              : "No nutrition"}
                          </span>
                        </span>
                      </button>
                    </div>
                  ))}
                </div>
              </>
            )}
          </section>

          <section className="card review-editor" aria-live="polite">
            {detailLoading && !createMode ? (
              <p className="search-note">Loading food details...</p>
            ) : !activeForm ? (
              <div className="review-empty">
                <strong>Select a food or add a new one.</strong>
                <span>
                  Edit nutrition, change status, or select several foods for a
                  batch action.
                </span>
              </div>
            ) : (
              <form className="review-form" onSubmit={handleSave}>
                <div className="section-head">
                  <div>
                    <p className="eyebrow">
                      {createMode
                        ? "New database entry"
                        : detail?.source === "off"
                          ? "Imported from Open Food Facts"
                          : detail?.source === "user"
                            ? "Photo estimate draft"
                            : "Curated food"}
                    </p>
                    <h2>{createMode ? "Add food" : detail?.name}</h2>
                    <p>
                      {createMode
                        ? "Nutrition values are per base amount."
                        : `Barcode ${
                            detail?.barcodes[0]?.barcode ?? "not recorded"
                          }`}
                    </p>
                  </div>
                  <span className="review-pill">
                    {createMode
                      ? "new"
                      : `${detail?.status}${
                          detail?.is_verified ? " · verified" : ""
                        }`}
                  </span>
                </div>

                <label className="field">
                  <span className="field-label">Food name</span>
                  <input
                    className="text-input"
                    type="text"
                    maxLength={160}
                    value={activeForm.name}
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
                      value={activeForm.brandName}
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
                      value={activeForm.category}
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
                      value={activeForm.subcategory}
                      onChange={(event) =>
                        setField("subcategory", event.target.value)
                      }
                    />
                  </label>

                  <label className="field">
                    <span className="field-label">Status</span>
                    <div className="select-wrap">
                      <select
                        value={activeForm.status}
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
                    value={activeForm.description}
                    onChange={(event) =>
                      setField("description", event.target.value)
                    }
                  />
                </label>

                <div className="review-grid review-macros">
                  <label className="field">
                    <span className="field-label">Calories</span>
                    <div className="input-shell">
                      <input
                        type="number"
                        min={0}
                        max={10000}
                        step={1}
                        value={activeForm.kcal}
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
                        value={activeForm.proteinG}
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
                        value={activeForm.carbsG}
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
                        value={activeForm.fatG}
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
                        value={activeForm.baseAmount}
                        onChange={(event) =>
                          setField("baseAmount", event.target.value)
                        }
                      />
                      <span className="unit">{activeForm.baseUnit}</span>
                    </div>
                  </label>

                  <label className="field">
                    <span className="field-label">Base unit</span>
                    <div className="select-wrap">
                      <select
                        value={activeForm.baseUnit}
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
                    checked={activeForm.isVerified}
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
                    {saving
                      ? "Saving..."
                      : createMode
                        ? "Create food"
                        : "Save changes"}
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
                    {createMode
                      ? "Create, approve and verify"
                      : "Approve and verify"}
                  </button>
                  {!createMode && (
                    <button
                      type="button"
                      className="text-button review-reject"
                      disabled={saving || activeForm.status === "rejected"}
                      onClick={() =>
                        handleSave(undefined, {
                          status: "rejected",
                          isVerified: false,
                        })
                      }
                    >
                      Reject
                    </button>
                  )}
                </div>

                {error && (
                  <p className="form-error" role="alert">
                    {error}
                  </p>
                )}

                {!createMode && (
                  <div className="review-history">
                    <div className="review-history-head">
                      <span className="field-label">Review history</span>
                      <span>
                        {history.length} note{history.length === 1 ? "" : "s"}
                      </span>
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
                              {" · "}
                              {new Date(item.created_at).toLocaleString(
                                "en-GB",
                              )}
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
                )}
              </form>
            )}
          </section>
        </div>
      </main>

      {confirm && (
        <div
          className="modal-backdrop"
          role="presentation"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) closeConfirm();
          }}
        >
          <form
            className="confirm-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="admin-confirm-title"
            onSubmit={handleConfirmSubmit}
          >
            <p className="eyebrow">Admin confirmation</p>
            <h2 id="admin-confirm-title">{confirm.title}</h2>
            <p>{confirm.description}</p>

            <label className="field">
              <span className="field-label">Confirmation password</span>
              <input
                className="text-input"
                type="password"
                autoFocus
                autoComplete="current-password"
                value={confirmPassword}
                onChange={(event) =>
                  setConfirmPassword(event.target.value)
                }
              />
            </label>

            {confirmError && (
              <p className="form-error" role="alert">
                {confirmError}
              </p>
            )}

            <div className="confirm-actions">
              <button
                type="button"
                className="text-button"
                onClick={closeConfirm}
                disabled={confirmBusy}
              >
                Cancel
              </button>
              <button
                type="submit"
                className={
                  confirm.danger
                    ? "save-button danger-button"
                    : "save-button"
                }
                disabled={confirmBusy}
              >
                {confirmBusy ? "Working..." : confirm.confirmLabel}
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
