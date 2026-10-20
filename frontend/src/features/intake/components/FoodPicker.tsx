import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type FormEvent,
} from "react";
import type { IScannerControls } from "@zxing/browser";
import {
  addCalorieEntry,
  ApiError,
  getFood,
  resolveBarcode,
  searchFoods,
} from "@/shared/api";
import {
  MEAL_OPTIONS,
  type CalorieEntry,
  type EntryUnit,
  type FoodDetail,
  type FoodSummary,
  type FoodVariant,
  type Meal,
} from "@/shared/types";

interface FoodPickerProps {
  date: string;
  onAdded: (entry: CalorieEntry) => void;
  onSessionExpired: () => void;
}

const STATE_LABELS: Record<string, string> = {
  raw: "Raw",
  cooked: "Cooked",
  as_sold: "As sold",
};

function variantLabel(variant: FoodVariant): string {
  return variant.label || STATE_LABELS[variant.state] || variant.state;
}

function reportError(
  caught: unknown,
  setError: (message: string) => void,
  onSessionExpired: () => void,
) {
  if (caught instanceof ApiError && caught.status === 401) {
    onSessionExpired();
    return;
  }
  if (caught instanceof ApiError) {
    setError(caught.message);
    return;
  }
  setError("Could not save that entry. Check your connection.");
}

export default function FoodPicker({
  date,
  onAdded,
  onSessionExpired,
}: FoodPickerProps) {
  const [mode, setMode] = useState<"search" | "barcode" | "manual">(
    "search",
  );
  const [meal, setMeal] = useState<Meal>("breakfast");
  const [query, setQuery] = useState("");
  const [barcode, setBarcode] = useState("");
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const scannerControlsRef = useRef<IScannerControls | null>(null);
  const lookupBarcodeRef = useRef<(code: string) => Promise<void>>(
    async () => {},
  );
  const [results, setResults] = useState<FoodSummary[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selected, setSelected] = useState<FoodDetail | null>(null);
  const [variantId, setVariantId] = useState<number | null>(null);
  const [quantity, setQuantity] = useState("100");
  const [unit, setUnit] = useState<EntryUnit>("g");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualName, setManualName] = useState("");
  const [manualCalories, setManualCalories] = useState("");
  const cameraAvailable =
    typeof window !== "undefined" &&
    window.isSecureContext &&
    typeof navigator.mediaDevices?.getUserMedia === "function";

  useEffect(() => {
    if (mode !== "search" || selected) return;

    const text = query.trim();
    if (text.length < 2) {
      setResults([]);
      setSearching(false);
      setSearchError(null);
      return;
    }

    let cancelled = false;
    setSearching(true);
    setSearchError(null);

    const timer = window.setTimeout(() => {
      searchFoods({ q: text, limit: 8 })
        .then((list) => {
          if (!cancelled) setResults(list.items);
        })
        .catch((caught) => {
          if (cancelled) return;
          if (caught instanceof ApiError && caught.status === 401) {
            onSessionExpired();
            return;
          }
          setSearchError("Could not search foods. Check the API and try again.");
        })
        .finally(() => {
          if (!cancelled) setSearching(false);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [query, mode, selected, onSessionExpired]);

  useEffect(() => {
    if (!scanning) return;

    let cancelled = false;
    setCameraError(null);

    async function startCamera() {
      if (!cameraAvailable) {
        setCameraError(
          "Camera scanning requires HTTPS or localhost. Type the barcode instead.",
        );
        setScanning(false);
        return;
      }

      const video = videoRef.current;
      if (!video) return;

      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        if (cancelled) return;

        const reader = new BrowserMultiFormatReader(undefined, {
          delayBetweenScanAttempts: 250,
          delayBetweenScanSuccess: 1000,
        });
        const controls = await reader.decodeFromConstraints(
          { video: { facingMode: { ideal: "environment" } } },
          video,
          (result, _error, control) => {
            if (!result || cancelled) return;
            cancelled = true;
            control.stop();
            scannerControlsRef.current = null;
            setScanning(false);

            const code = result.getText().replace(/\D/g, "");
            if (code.length >= 8 && code.length <= 14) {
              void lookupBarcodeRef.current(code);
            } else {
              setCameraError(
                "That code was not a valid barcode. Try again or type it.",
              );
            }
          },
        );

        if (cancelled) {
          controls.stop();
          return;
        }
        scannerControlsRef.current = controls;
      } catch {
        if (cancelled) return;
        setCameraError(
          "Camera access failed. Allow camera access or type the barcode.",
        );
        setScanning(false);
      }
    }

    void startCamera();

    return () => {
      cancelled = true;
      scannerControlsRef.current?.stop();
      scannerControlsRef.current = null;
    };
  }, [scanning, cameraAvailable]);

  const selectedVariant =
    selected?.variants.find((variant) => variant.id === variantId) ??
    selected?.variants[0] ??
    null;

  const packServing =
    selectedVariant?.servings.find((serving) => serving.is_default) ??
    selectedVariant?.servings[0] ??
    null;

  const packUnitLabel =
    packServing?.label.replace(/^1\s+/, "") ?? "pack";

  const units = selectedVariant
    ? Array.from(
        new Set<EntryUnit>([
          selectedVariant.base_unit,
          ...(packServing ? (["pack"] as EntryUnit[]) : []),
        ]),
      )
    : [];

  const preview = useMemo(() => {
    if (!selectedVariant) return 0;
    const amount = Number(quantity);
    if (!Number.isFinite(amount) || amount <= 0) return 0;
    const grams =
      unit === "pack"
        ? packServing
          ? packServing.amount * amount
          : 0
        : amount;
    return Math.round((selectedVariant.kcal * grams) / selectedVariant.base_amount);
  }, [selectedVariant, quantity, unit, packServing]);

  function stopScanning() {
    scannerControlsRef.current?.stop();
    scannerControlsRef.current = null;
    setScanning(false);
  }

  function switchMode(next: "search" | "barcode" | "manual") {
    stopScanning();
    setMode(next);
    setError(null);
  }

  function resetSearch() {
    stopScanning();
    setSelected(null);
    setVariantId(null);
    setQuery("");
    setResults([]);
    setSearchError(null);
    setQuantity("100");
    setUnit("g");
  }

  function applyFood(detail: FoodDetail) {
    const variant =
      detail.variants.find((item) => item.is_default) ??
      detail.variants[0] ??
      null;
    setSelected(detail);
    setVariantId(variant?.id ?? null);
    setUnit(variant?.base_unit ?? "g");
    setQuantity(String(variant?.base_amount ?? 100));
    setQuery(detail.name);
    setResults([]);
    setSearchError(null);
  }

  async function chooseFood(food: FoodSummary) {
    setError(null);
    setSearchError(null);
    setResults([]);
    setSearching(true);
    setQuery(food.name);

    try {
      const detail = await getFood(food.id);
      applyFood(detail);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      setSearchError("Could not open that food. Try another result.");
    } finally {
      setSearching(false);
    }
  }

  async function lookupBarcode(code: string) {
    stopScanning();
    setError(null);
    setCameraError(null);

    const digits = code.replace(/\D/g, "");
    if (digits.length < 8 || digits.length > 14) {
      setError("Enter an 8 to 14 digit barcode.");
      return;
    }

    setBarcode(digits);
    setBarcodeBusy(true);
    try {
      const detail = await resolveBarcode(digits);
      applyFood(detail);
      setBarcode("");
      setMode("search");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      if (caught instanceof ApiError) {
        setError(caught.message);
        return;
      }
      setError("Could not look up that barcode. Check your connection.");
    } finally {
      setBarcodeBusy(false);
    }
  }

  lookupBarcodeRef.current = lookupBarcode;

  async function handleBarcodeLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await lookupBarcode(barcode);
  }

  function chooseVariant(variant: FoodVariant) {
    setVariantId(variant.id);
    setUnit(variant.base_unit);
    setQuantity(String(variant.base_amount));
  }

  function chooseUnit(next: EntryUnit) {
    setUnit(next);
    if (next === "pack") setQuantity("1");
    else setQuantity(String(selectedVariant?.base_amount ?? 100));
  }

  async function handleAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!selectedVariant) {
      setError("Choose a food from the search results first.");
      return;
    }

    const amount = Number(quantity);
    if (!Number.isFinite(amount) || amount <= 0) {
      setError("Enter a quantity greater than zero.");
      return;
    }

    setSaving(true);
    try {
      const created = await addCalorieEntry({
        date,
        meal,
        variant_id: selectedVariant.id,
        quantity: amount,
        unit,
      });
      onAdded(created);
      resetSearch();
    } catch (caught) {
      reportError(caught, setError, onSessionExpired);
    } finally {
      setSaving(false);
    }
  }

  async function handleManualAdd(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const name = manualName.trim();
    const calories = Number(manualCalories);

    if (!name) {
      setError("Add a food name first.");
      return;
    }
    if (!Number.isFinite(calories) || calories < 0 || calories > 10000) {
      setError("Calories must be a number between 0 and 10,000.");
      return;
    }

    setSaving(true);
    try {
      const created = await addCalorieEntry({
        date,
        meal,
        name,
        calories: Math.round(calories),
      });
      onAdded(created);
      setManualName("");
      setManualCalories("");
    } catch (caught) {
      reportError(caught, setError, onSessionExpired);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="card form-card food-card">
      <div className="section-head">
        <div>
          <h2>Add food</h2>
          <p>Search the Indian food database or add a custom entry.</p>
        </div>
        <div className="picker-mode" role="group" aria-label="Entry mode">
          <button
            type="button"
            className={mode === "search" ? "active" : ""}
            aria-pressed={mode === "search"}
            onClick={() => switchMode("search")}
          >
            Search
          </button>
          <button
            type="button"
            className={mode === "barcode" ? "active" : ""}
            aria-pressed={mode === "barcode"}
            onClick={() => switchMode("barcode")}
          >
            Barcode
          </button>
          <button
            type="button"
            className={mode === "manual" ? "active" : ""}
            aria-pressed={mode === "manual"}
            onClick={() => switchMode("manual")}
          >
            Manual
          </button>
        </div>
      </div>

      <div className="meal-picker" role="group" aria-label="Meal">
        {MEAL_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            className={meal === option.value ? "active" : ""}
            aria-pressed={meal === option.value}
            onClick={() => setMeal(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {mode === "search" ? (
        <>
          <div className="food-search">
            <label className="field">
              <span className="field-label">Search foods</span>
              <input
                className="text-input"
                type="text"
                name="food-search"
                autoComplete="off"
                placeholder="e.g. dal, roti, paneer, maggi"
                value={query}
                onChange={(event) => {
                  setSelected(null);
                  setQuery(event.target.value);
                }}
              />
            </label>

            {!selected && query.trim().length >= 2 && (
              <div className="search-results" role="listbox">
                {searching ? (
                  <p className="search-note">Searching…</p>
                ) : searchError ? (
                  <p className="search-note error">{searchError}</p>
                ) : results.length === 0 ? (
                  <p className="search-note">
                    No foods found. Try another name or use manual entry.
                  </p>
                ) : (
                  results.map((food) => (
                    <button
                      key={food.id}
                      type="button"
                      className="search-result"
                      role="option"
                      aria-selected={false}
                      onClick={() => chooseFood(food)}
                    >
                      <span className="result-main">
                        <strong>{food.name}</strong>
                        <span>
                          {[food.brand?.name, food.category]
                            .filter(Boolean)
                            .join(" · ")}
                        </span>
                      </span>
                      <span className="result-kcal">
                        {food.default_variant
                          ? `${food.default_variant.kcal} kcal / ${food.default_variant.base_amount}${food.default_variant.base_unit}`
                          : ""}
                      </span>
                    </button>
                  ))
                )}
              </div>
            )}
          </div>

          {selected && selectedVariant && (
            <form className="picked-food" onSubmit={handleAdd}>
              <div className="picked-head">
                <div>
                  <h3>{selected.name}</h3>
                  <p>
                    {[
                      selected.brand?.name,
                      selected.category,
                      selected.is_verified ? "Verified" : "Unverified",
                    ]
                      .filter(Boolean)
                      .join(" · ")}
                  </p>
                </div>
                <button
                  type="button"
                  className="text-button"
                  onClick={resetSearch}
                >
                  Change
                </button>
              </div>

              {selected.variants.length > 1 && (
                <div className="variant-picker" role="group" aria-label="Variant">
                  {selected.variants.map((variant) => (
                    <button
                      key={variant.id}
                      type="button"
                      className={
                        selectedVariant.id === variant.id ? "active" : ""
                      }
                      aria-pressed={selectedVariant.id === variant.id}
                      onClick={() => chooseVariant(variant)}
                    >
                      <strong>{variantLabel(variant)}</strong>
                      <span>
                        {variant.kcal} kcal / {variant.base_amount}
                        {variant.base_unit}
                      </span>
                    </button>
                  ))}
                </div>
              )}

              <div className="quantity-row">
                <label className="field">
                  <span className="field-label">Quantity</span>
                  <div className="input-shell">
                    <input
                      type="number"
                      name="quantity"
                      inputMode="decimal"
                      min={0.1}
                      max={10000}
                      step={1}
                      value={quantity}
                      onChange={(event) => setQuantity(event.target.value)}
                    />
                    <span className="unit">
                      {unit === "pack" ? packUnitLabel : unit}
                    </span>
                  </div>
                </label>

                <div className="unit-picker" role="group" aria-label="Unit">
                  {units.map((option) => (
                    <button
                      key={option}
                      type="button"
                      className={unit === option ? "active" : ""}
                      aria-pressed={unit === option}
                      onClick={() => chooseUnit(option)}
                    >
                      {option === "pack" ? packServing?.label : option}
                    </button>
                  ))}
                </div>
              </div>

              {unit === "pack" && packServing && (
                <p className="pack-note">
                  {packServing.label} = {packServing.amount} {packServing.unit}
                </p>
              )}

              <div className="entry-preview">
                <span>Estimated</span>
                <strong>{preview.toLocaleString("en-GB")} kcal</strong>
              </div>

              <button
                type="submit"
                className="save-button add-entry-button"
                disabled={saving}
              >
                {saving ? "Adding…" : "Add entry"}
              </button>
            </form>
          )}
        </>
      ) : mode === "barcode" ? (
        <form className="food-form" onSubmit={handleBarcodeLookup} noValidate>
          <label className="field">
            <span className="field-label">Barcode</span>
            <input
              className="text-input"
              type="text"
              name="barcode"
              inputMode="numeric"
              autoComplete="off"
              maxLength={14}
              placeholder="e.g. 8901063012345"
              value={barcode}
              onChange={(event) =>
                setBarcode(event.target.value.replace(/\D/g, ""))
              }
            />
          </label>

          <div className="barcode-actions">
            <button
              type="submit"
              className="save-button add-entry-button"
              disabled={barcodeBusy}
            >
              {barcodeBusy ? "Looking up..." : "Look up barcode"}
            </button>
            {!scanning && (
              <button
                type="button"
                className="scan-button"
                disabled={barcodeBusy || !cameraAvailable}
                title={
                  cameraAvailable
                    ? undefined
                    : "Camera scanning requires HTTPS or localhost"
                }
                onClick={() => {
                  setError(null);
                  setCameraError(null);
                  setScanning(true);
                }}
              >
                Scan with camera
              </button>
            )}
          </div>

          {scanning && (
            <div className="scanner-shell">
              <video
                ref={videoRef}
                className="scanner-video"
                muted
                playsInline
              />
              <button
                type="button"
                className="text-button"
                onClick={stopScanning}
              >
                Stop camera
              </button>
            </div>
          )}

          {cameraError && (
            <p className="search-note error barcode-note">{cameraError}</p>
          )}

          <p className="search-note barcode-note">
            {cameraAvailable
              ? "Camera scanning needs permission. New barcodes are looked up on Open Food Facts and saved as unverified foods."
              : "Camera scanning is unavailable over plain HTTP. Use manual barcode entry, or open the app on localhost/HTTPS."}
          </p>
        </form>
      ) : (
        <form className="food-form" onSubmit={handleManualAdd} noValidate>
          <label className="field">
            <span className="field-label">Food</span>
            <input
              className="text-input"
              type="text"
              name="food"
              maxLength={120}
              placeholder="e.g. Oats with banana"
              value={manualName}
              onChange={(event) => setManualName(event.target.value)}
            />
          </label>

          <div className="food-form-row">
            <label className="field">
              <span className="field-label">Calories</span>
              <div className="input-shell">
                <input
                  type="number"
                  name="calories"
                  inputMode="numeric"
                  min={0}
                  max={10000}
                  step={1}
                  placeholder="320"
                  value={manualCalories}
                  onChange={(event) => setManualCalories(event.target.value)}
                />
                <span className="unit">kcal</span>
              </div>
            </label>

            <button
              type="submit"
              className="save-button add-entry-button"
              disabled={saving}
            >
              {saving ? "Adding…" : "Add entry"}
            </button>
          </div>
        </form>
      )}

      {error && (
        <p className="form-error" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
