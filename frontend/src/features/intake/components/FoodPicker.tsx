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
  analyzePhotoMeal,
  ApiError,
  getFood,
  getPhotoMeal,
  getPhotoMealConfig,
  listPhotoMeals,
  scanBarcode,
  searchFoods,
} from "@/shared/api";
import {
  type BarcodeCache,
  readBarcodeCache,
  writeBarcodeCache,
} from "@/shared/lib";
import {
  MEAL_OPTIONS,
  type BarcodeScanResult,
  type CalorieEntry,
  type EntryUnit,
  type FoodDetail,
  type FoodSummary,
  type FoodVariant,
  type Meal,
  type PhotoMealConfig,
  type PhotoMealJob,
} from "@/shared/types";

interface FoodPickerProps {
  date: string;
  onAdded: (entries: CalorieEntry[]) => void;
  onRefresh: () => void;
  onSessionExpired: () => void;
}

const MAX_PHOTO_BYTES = 8 * 1024 * 1024;
const PHOTO_IN_PROGRESS = new Set(["pending", "processing"]);

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
  onRefresh,
  onSessionExpired,
}: FoodPickerProps) {
  const [mode, setMode] = useState<
    "search" | "camera" | "photo" | "manual"
  >("search");
  const [meal, setMeal] = useState<Meal>("breakfast");
  const [query, setQuery] = useState("");
  const [barcode, setBarcode] = useState("");
  const [barcodeBusy, setBarcodeBusy] = useState(false);
  const [cameraReady, setCameraReady] = useState(false);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [detectedBarcode, setDetectedBarcode] = useState<string | null>(null);
  const [barcodeHint, setBarcodeHint] = useState("");
  const [barcodeQueued, setBarcodeQueued] = useState(false);
  const [pickerNotice, setPickerNotice] = useState<string | null>(null);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const cameraControlsRef = useRef<IScannerControls | null>(null);
  const barcodeLockRef = useRef<string | null>(null);
  const barcodeCacheRef = useRef<BarcodeCache>(new Map());
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
  const [photoConfig, setPhotoConfig] = useState<PhotoMealConfig | null>(null);
  const [photoPreview, setPhotoPreview] = useState<string | null>(null);
  const [photoJob, setPhotoJob] = useState<PhotoMealJob | null>(null);
  const [photoBusy, setPhotoBusy] = useState(false);
  const cameraInputRef = useRef<HTMLInputElement | null>(null);
  const galleryInputRef = useRef<HTMLInputElement | null>(null);
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
    if (mode !== "camera") return;

    let cancelled = false;
    setCameraError(null);
    setCameraReady(false);

    async function startCamera() {
      if (!cameraAvailable) {
        setCameraError(
          "Live camera requires HTTPS or localhost. You can still upload a photo.",
        );
        return;
      }

      const video = videoRef.current;
      if (!video) return;

      try {
        const { BrowserMultiFormatReader } = await import("@zxing/browser");
        if (cancelled) return;

        const reader = new BrowserMultiFormatReader(undefined, {
          delayBetweenScanAttempts: 250,
          delayBetweenScanSuccess: 1200,
        });
        const controls = await reader.decodeFromConstraints(
          { video: { facingMode: { ideal: "environment" } } },
          video,
          (result) => {
            if (!result || cancelled) return;

            const code = result.getText().replace(/\D/g, "");
            if (code.length < 8 || code.length > 14) return;
            if (barcodeLockRef.current === code) return;

            barcodeLockRef.current = code;
            const cached = readBarcodeCache(barcodeCacheRef.current, code);
            setDetectedBarcode(code);
            setBarcodeQueued(cached?.status === "queued");
            setBarcodeHint(
              cached
                ? "Barcode cached from this session. Tap Add to use it."
                : "Barcode detected. Tap Add to look it up.",
            );
          },
        );

        if (cancelled) {
          controls.stop();
          return;
        }
        cameraControlsRef.current = controls;
        setCameraReady(true);
      } catch {
        if (cancelled) return;
        setCameraError(
          "Camera access failed. Allow camera access or upload a photo instead.",
        );
        setCameraReady(false);
      }
    }

    void startCamera();

    return () => {
      cancelled = true;
      cameraControlsRef.current?.stop();
      cameraControlsRef.current = null;
      setCameraReady(false);
    };
  }, [mode, cameraAvailable]);

  useEffect(() => {
    let cancelled = false;

    getPhotoMealConfig()
      .then((config) => {
        if (!cancelled) setPhotoConfig(config);
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          onSessionExpired();
        }
      });

    return () => {
      cancelled = true;
    };
  }, [onSessionExpired]);

  useEffect(() => {
    let cancelled = false;

    listPhotoMeals(10)
      .then((jobs) => {
        if (cancelled) return;
        const active = jobs.find(
          (job) => job.date === date && PHOTO_IN_PROGRESS.has(job.status),
        );
        if (active) {
          setPhotoJob(active);
          return;
        }
        setPhotoJob((current) =>
          current && current.date === date ? current : null,
        );
      })
      .catch((caught) => {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          onSessionExpired();
        }
      });

    return () => {
      cancelled = true;
    };
  }, [date, onSessionExpired]);

  const photoJobId = photoJob?.id;
  const photoJobStatus = photoJob?.status;

  useEffect(() => {
    if (!photoJobId || !photoJobStatus || !PHOTO_IN_PROGRESS.has(photoJobStatus)) {
      return;
    }

    const jobId = photoJobId;
    let cancelled = false;

    async function poll() {
      try {
        const next = await getPhotoMeal(jobId);
        if (cancelled) return;
        setPhotoJob(next);
        if (next.status === "completed") {
          setMode("photo");
          onRefresh();
        } else if (next.status === "failed") {
          setError(next.error ?? "Photo analysis failed. Try another photo.");
        }
      } catch (caught) {
        if (cancelled) return;
        if (caught instanceof ApiError && caught.status === 401) {
          onSessionExpired();
        }
      }
    }

    void poll();
    const timer = window.setInterval(() => {
      void poll();
    }, 2000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [photoJobId, photoJobStatus, onSessionExpired, onRefresh]);

  useEffect(() => {
    return () => {
      if (photoPreview) URL.revokeObjectURL(photoPreview);
    };
  }, [photoPreview]);

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

  const photoActive = Boolean(
    photoBusy || (photoJob && PHOTO_IN_PROGRESS.has(photoJob.status)),
  );
  const selectedMealLabel =
    MEAL_OPTIONS.find((option) => option.value === meal)?.label ?? meal;

  function dismissBarcode() {
    setDetectedBarcode(null);
    setBarcodeHint("");
    setBarcodeQueued(false);
    barcodeLockRef.current = null;
  }

  function switchMode(next: "search" | "camera" | "manual") {
    dismissBarcode();
    setMode(next);
    setError(null);
    setCameraError(null);
    setPickerNotice(null);
  }

  function resetSearch() {
    setSelected(null);
    setVariantId(null);
    setQuery("");
    setResults([]);
    setSearchError(null);
    setQuantity("100");
    setUnit("g");
  }

  async function startPhotoAnalysis(file: File) {
    setPhotoBusy(true);
    setError(null);
    try {
      const job = await analyzePhotoMeal({ date, meal, image: file });
      setPhotoJob(job);
      if (job.status === "completed") onRefresh();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      if (caught instanceof ApiError) {
        setError(caught.message);
        return;
      }
      setError("Could not analyze that photo. Check your connection.");
    } finally {
      setPhotoBusy(false);
    }
  }

  function choosePhoto(file: File | null) {
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Choose a JPEG, PNG, or WebP photo.");
      return;
    }
    if (file.size > MAX_PHOTO_BYTES) {
      setError("That photo is too large. Use an image under 8 MB.");
      return;
    }

    setPhotoPreview(URL.createObjectURL(file));
    setPhotoJob(null);
    setError(null);
    setMode("photo");
    void startPhotoAnalysis(file);
  }

  function resetPhoto() {
    if (photoJob && PHOTO_IN_PROGRESS.has(photoJob.status)) return;
    setPhotoPreview(null);
    setPhotoJob(null);
    setError(null);
  }

  function captureFrame() {
    const video = videoRef.current;
    if (!video || !cameraReady || video.videoWidth === 0) {
      cameraInputRef.current?.click();
      return;
    }

    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    const context = canvas.getContext("2d");
    if (!context) {
      setError("Could not capture the camera frame. Try uploading a photo.");
      return;
    }

    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) {
          setError("Could not capture the camera frame. Try uploading a photo.");
          return;
        }
        choosePhoto(
          new File([blob], `meal-${Date.now()}.jpg`, {
            type: "image/jpeg",
          }),
        );
      },
      "image/jpeg",
      0.9,
    );
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

  function applyBarcodeResult(result: BarcodeScanResult) {
    if (result.status === "queued") {
      setBarcodeQueued(true);
      setBarcodeHint(
        "No product match yet. This barcode was submitted for admin review.",
      );
      setPickerNotice(
        `Barcode ${result.barcode} is queued for admin review. You can add the food from the database after approval.`,
      );
      return;
    }

    applyFood(result.food);
    setBarcode("");
    setDetectedBarcode(null);
    setBarcodeHint("");
    setBarcodeQueued(false);
    barcodeLockRef.current = null;
    setPickerNotice(
      result.status === "database"
        ? "Found in the food database."
        : "Imported from Open Food Facts and submitted for review. You can adjust the serving and add it now.",
    );
    setMode("search");
  }

  async function lookupBarcode(code: string) {
    setError(null);
    setCameraError(null);
    setPickerNotice(null);

    const digits = code.replace(/\D/g, "");
    if (digits.length < 8 || digits.length > 14) {
      setError("Enter an 8 to 14 digit barcode.");
      return;
    }

    setBarcode(digits);
    setBarcodeBusy(true);
    try {
      const cache = barcodeCacheRef.current;
      const cached = readBarcodeCache(cache, digits);
      const result = cached ?? (await scanBarcode(digits));
      writeBarcodeCache(cache, digits, result);
      applyBarcodeResult(result);
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

  async function addDetectedBarcode() {
    const code = detectedBarcode;
    if (!code || barcodeBusy) return;
    if (barcodeQueued) {
      dismissBarcode();
      return;
    }

    const cache = barcodeCacheRef.current;
    const cached = readBarcodeCache(cache, code);
    if (cached && cached.status !== "queued") {
      applyBarcodeResult(cached);
      return;
    }

    setBarcodeBusy(true);
    setBarcodeHint("Looking up this barcode...");
    try {
      const result = await scanBarcode(code);
      writeBarcodeCache(cache, code, result);
      applyBarcodeResult(result);
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        onSessionExpired();
        return;
      }
      setBarcodeHint(
        caught instanceof ApiError
          ? caught.message
          : "Could not look up that barcode. Check your connection.",
      );
    } finally {
      setBarcodeBusy(false);
    }
  }

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
    if (amount > 10000) {
      setError("Quantity must be 10,000 or less.");
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
      onAdded([created]);
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
      onAdded([created]);
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
            className={
              mode === "camera" || mode === "photo" ? "active" : ""
            }
            aria-pressed={mode === "camera" || mode === "photo"}
            onClick={() => switchMode("camera")}
          >
            Scan
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
            disabled={photoActive}
            onClick={() => setMeal(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>

      {pickerNotice && (
        <p className="picker-notice" role="status">
          {pickerNotice}
        </p>
      )}

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
                      min={0}
                      max={10000}
                      step="any"
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
      ) : mode === "camera" ? (
        <div className="camera-panel">
          <input
            ref={cameraInputRef}
            className="visually-hidden"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              event.target.value = "";
              choosePhoto(file);
            }}
          />
          <input
            ref={galleryInputRef}
            className="visually-hidden"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              event.target.value = "";
              choosePhoto(file);
            }}
          />

          {!cameraAvailable ? (
            <div className="camera-unavailable">
              <p className="search-note photo-note">
                {cameraError ??
                  "Live camera requires HTTPS or localhost. You can still upload a photo."}
              </p>
              <div className="photo-actions">
                <button
                  type="button"
                  className="save-button add-entry-button"
                  disabled={photoActive || photoConfig?.enabled === false}
                  onClick={() => cameraInputRef.current?.click()}
                >
                  Use device camera
                </button>
                <button
                  type="button"
                  className="scan-button"
                  disabled={photoActive || photoConfig?.enabled === false}
                  onClick={() => galleryInputRef.current?.click()}
                >
                  Upload image
                </button>
              </div>
            </div>
          ) : (
            <div className="camera-stage">
              <video
                ref={videoRef}
                className="camera-video"
                muted
                playsInline
                autoPlay
              />

              {!cameraReady && !cameraError && (
                <div className="camera-starting" role="status">
                  <span className="photo-spinner" aria-hidden="true" />
                  Starting camera...
                </div>
              )}

              {cameraError && (
                <div className="camera-error" role="alert">
                  {cameraError}
                </div>
              )}

              {detectedBarcode && (
                <div className="barcode-pop" role="status">
                  <div className="barcode-pop-main">
                    <span>Barcode detected</span>
                    <strong>{detectedBarcode}</strong>
                    <span>{barcodeHint}</span>
                  </div>
                  <div className="barcode-pop-actions">
                    <button
                      type="button"
                      className="save-button"
                      disabled={barcodeBusy}
                      onClick={addDetectedBarcode}
                    >
                      {barcodeQueued
                        ? "Close"
                        : barcodeBusy
                          ? "Checking..."
                          : "Add"}
                    </button>
                    {!barcodeQueued && (
                      <button
                        type="button"
                        className="text-button"
                        disabled={barcodeBusy}
                        onClick={dismissBarcode}
                      >
                        Dismiss
                      </button>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          <div className="photo-actions camera-controls">
            <button
              type="button"
              className="save-button add-entry-button"
              disabled={
                photoActive ||
                photoConfig?.enabled === false ||
                !cameraReady
              }
              onClick={captureFrame}
            >
              {photoActive ? "Analyzing..." : "Capture meal"}
            </button>
            <button
              type="button"
              className="scan-button"
              disabled={photoActive || photoConfig?.enabled === false}
              onClick={() => galleryInputRef.current?.click()}
            >
              Upload image
            </button>
          </div>

          <p className="search-note photo-note">
            Barcodes are detected automatically and appear above the capture
            button. Tap Add to use the product, or Capture meal to send the
            current frame to the vision model for {selectedMealLabel}.
          </p>

          {photoConfig?.enabled === false && (
            <p className="search-note photo-note">
              AI photo analysis is not configured on this server, but barcode
              detection still works.
            </p>
          )}

          <form
            className="scan-barcode-form"
            onSubmit={handleBarcodeLookup}
            noValidate
          >
            <label className="field">
              <span className="field-label">
                Barcode fallback (type manually)
              </span>
              <input
                className="text-input"
                type="text"
                name="scan-barcode"
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
            <button
              type="submit"
              className="scan-button"
              disabled={barcodeBusy}
            >
              {barcodeBusy ? "Looking up..." : "Look up barcode"}
            </button>
          </form>
        </div>
      ) : mode === "photo" ? (
        <div className="photo-panel">
          <input
            ref={cameraInputRef}
            className="visually-hidden"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            capture="environment"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              event.target.value = "";
              choosePhoto(file);
            }}
          />
          <input
            ref={galleryInputRef}
            className="visually-hidden"
            type="file"
            accept="image/jpeg,image/png,image/webp"
            onChange={(event) => {
              const file = event.target.files?.[0] ?? null;
              event.target.value = "";
              choosePhoto(file);
            }}
          />

          {photoConfig?.enabled === false ? (
            <p className="search-note photo-note">
              Photo analysis is not configured on this server. Add an image
              analysis API key to enable it.
            </p>
          ) : (
            <div className="photo-actions">
              <button
                type="button"
                className="save-button add-entry-button"
                disabled={photoActive}
                onClick={() => switchMode("camera")}
              >
                Open camera
              </button>
              <button
                type="button"
                className="scan-button"
                disabled={photoActive}
                onClick={() => galleryInputRef.current?.click()}
              >
                Choose image
              </button>
            </div>
          )}

          {photoPreview && (
            <img
              className="photo-preview"
              src={photoPreview}
              alt="Meal preview"
            />
          )}

          {photoBusy && (
            <div className="photo-status" role="status">
              <span className="photo-spinner" aria-hidden="true" />
              Uploading photo and starting analysis...
            </div>
          )}

          {!photoBusy && photoJob && PHOTO_IN_PROGRESS.has(photoJob.status) && (
            <div className="photo-status" role="status">
              <span className="photo-spinner" aria-hidden="true" />
              Analyzing your meal. This can take a few seconds.
            </div>
          )}

          {photoJob?.status === "completed" && (
            <div className="photo-result">
              <div className="photo-result-head">
                <div>
                  <strong>
                    {photoJob.items.length} item
                    {photoJob.items.length === 1 ? "" : "s"} added to{" "}
                    {MEAL_OPTIONS.find(
                      (option) => option.value === photoJob.meal,
                    )?.label ?? photoJob.meal}
                  </strong>
                  <span>Estimates were saved to your day.</span>
                </div>
                <button
                  type="button"
                  className="text-button"
                  onClick={() => {
                    resetPhoto();
                    switchMode("camera");
                  }}
                >
                  Retake
                </button>
              </div>

              <ul className="photo-items">
                {photoJob.items.map((item, index) => (
                  <li key={`${item.name}-${index}`}>
                    <span>
                      <strong>{item.name}</strong>
                      <span>
                        {Math.round(item.portion_g)} g ·{" "}
                        {item.protein_g.toFixed(1)} g protein ·{" "}
                        {item.carbs_g.toFixed(1)} g carbs ·{" "}
                        {item.fat_g.toFixed(1)} g fat ·{" "}
                        {item.matched ? "database match" : "draft for review"}
                      </span>
                    </span>
                    <strong>{item.calories} kcal</strong>
                  </li>
                ))}
              </ul>

              <p className="search-note photo-note">
                AI portions are estimates. Remove or adjust individual entries
                from the meal list below if needed.
              </p>
            </div>
          )}

          {photoJob?.status === "failed" && (
            <div className="photo-result">
              <div className="photo-result-head">
                <div>
                  <strong>Photo analysis failed</strong>
                  <span>{photoJob.error}</span>
                </div>
                <button
                  type="button"
                  className="text-button"
                  onClick={resetPhoto}
                >
                  Clear
                </button>
              </div>
            </div>
          )}
        </div>
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
