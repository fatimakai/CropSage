"use client";

import dynamic from "next/dynamic";
import {
  ArrowLeft,
  ArrowRight,
  CalendarDays,
  Check,
  ClipboardCheck,
  Droplets,
  FlaskConical,
  LoaderCircle,
  LocateFixed,
  MapPin,
  MapPinned,
  Pencil,
  Save,
} from "lucide-react";
import { useState } from "react";

import {
  createFarmProfileResponseSchema,
  farmLocationSchema,
  farmProfileDraftSchema,
  irrigationInputSchema,
  plantingPlanSchema,
  type FarmProfileDraft,
} from "@/lib/contracts";

const FarmMap = dynamic(
  () => import("@/components/farm-profile/farm-map").then((module) => module.FarmMap),
  {
    ssr: false,
    loading: () => <div className="map-loading">Loading farm map...</div>,
  },
);

const steps = [
  { label: "Location", icon: MapPin },
  { label: "Planting plan", icon: CalendarDays },
  { label: "Water", icon: Droplets },
  { label: "Field evidence", icon: FlaskConical },
  { label: "Review", icon: ClipboardCheck },
];

type LocationSource = "map_pin" | "gps" | "demo_farm" | "manual_coordinates";
type PlantingMode = "month" | "date";

type FormState = {
  farmName: string;
  locationLabel: string;
  latitude: string;
  longitude: string;
  locationSource: LocationSource;
  plantingMode: PlantingMode;
  plannedDate: string;
  plannedMonth: string;
  flexibilityDays: string;
  irrigationAvailability: "yes" | "no" | "unknown";
  irrigationReliability: "reliable" | "limited" | "seasonal" | "unreliable" | "unknown";
  irrigationMethod: "drip" | "center_pivot" | "sprinkler" | "furrow" | "flood" | "subsurface" | "other" | "unknown";
  waterSource: "well" | "canal" | "pond" | "municipal" | "captured_rainwater" | "multiple" | "other" | "unknown";
  wellCapacity: string;
  canalCapacity: string;
  canalCapacityUnit: "gpm" | "cfs" | "liters_per_second" | "cubic_meters_per_hour" | "gallons_per_day" | "acre_feet_per_year";
  irrigationNotes: string;
  includeTexture: boolean;
  soilTexture: string;
  soilTextureSource: "farmer" | "soil_test_report";
  soilTextureDate: string;
  includePh: boolean;
  laboratoryPh: string;
  phTestedAt: string;
  laboratoryName: string;
  reportReference: string;
  includeMoisture: boolean;
  soilMoisture: "very_dry" | "dry" | "adequate" | "wet" | "saturated" | "unknown";
  soilMoistureSource: "farmer_observation" | "sensor" | "other" | "unknown";
  moistureNotes: string;
  includeRainfall: boolean;
  rainfallAmountMm: string;
  rainfallPeriodDays: string;
  rainfallEndDate: string;
  rainfallSource: "farmer" | "farm_rain_gauge";
  includeGoal: boolean;
  primaryGoal: "maximize_yield" | "reduce_water_use" | "heat_resilience" | "lower_input_cost" | "market_crop" | "household_use" | "soil_health" | "other";
  goalNotes: string;
};

const initialForm: FormState = {
  farmName: "",
  locationLabel: "",
  latitude: "",
  longitude: "",
  locationSource: "manual_coordinates",
  plantingMode: "month",
  plannedDate: "",
  plannedMonth: "",
  flexibilityDays: "30",
  irrigationAvailability: "unknown",
  irrigationReliability: "unknown",
  irrigationMethod: "unknown",
  waterSource: "unknown",
  wellCapacity: "",
  canalCapacity: "",
  canalCapacityUnit: "gpm",
  irrigationNotes: "",
  includeTexture: false,
  soilTexture: "",
  soilTextureSource: "farmer",
  soilTextureDate: "",
  includePh: false,
  laboratoryPh: "",
  phTestedAt: "",
  laboratoryName: "",
  reportReference: "",
  includeMoisture: false,
  soilMoisture: "unknown",
  soilMoistureSource: "farmer_observation",
  moistureNotes: "",
  includeRainfall: false,
  rainfallAmountMm: "",
  rainfallPeriodDays: "7",
  rainfallEndDate: "",
  rainfallSource: "farmer",
  includeGoal: false,
  primaryGoal: "maximize_yield",
  goalNotes: "",
};

function requiredNumber(value: string) {
  return value.trim() === "" ? Number.NaN : Number(value);
}

function optionalNumber(value: string) {
  return value.trim() === "" ? undefined : Number(value);
}

function optionalText(value: string) {
  const trimmed = value.trim();
  return trimmed || undefined;
}

function buildLocation(form: FormState) {
  return farmLocationSchema.parse({
    latitude: requiredNumber(form.latitude),
    longitude: requiredNumber(form.longitude),
    source: form.locationSource,
    farm_name: optionalText(form.farmName),
    location_label: optionalText(form.locationLabel),
  });
}

function buildPlanting(form: FormState) {
  return plantingPlanSchema.parse({
    planned_date: form.plantingMode === "date" ? optionalText(form.plannedDate) : undefined,
    planned_month: form.plantingMode === "month" ? optionalText(form.plannedMonth) : undefined,
    flexibility_days: optionalNumber(form.flexibilityDays),
  });
}

function buildIrrigation(form: FormState) {
  if (form.irrigationAvailability === "no") {
    return irrigationInputSchema.parse({
      availability: "no",
      reliability: "not_applicable",
      notes: optionalText(form.irrigationNotes),
    });
  }

  if (form.irrigationAvailability === "unknown") {
    return irrigationInputSchema.parse({
      availability: "unknown",
      reliability: "unknown",
      notes: optionalText(form.irrigationNotes),
    });
  }

  const hasWell = form.waterSource === "well" || form.waterSource === "multiple";
  const hasCanal = form.waterSource === "canal" || form.waterSource === "multiple";

  return irrigationInputSchema.parse({
    availability: "yes",
    reliability: form.irrigationReliability,
    method: form.irrigationMethod,
    water_source: form.waterSource,
    well_pumping_capacity_gpm: hasWell ? optionalNumber(form.wellCapacity) : undefined,
    canal_allocation_or_capacity:
      hasCanal && form.canalCapacity.trim()
        ? {
            value: requiredNumber(form.canalCapacity),
            unit: form.canalCapacityUnit,
            source: "farmer",
          }
        : undefined,
    notes: optionalText(form.irrigationNotes),
  });
}

function buildDraft(form: FormState): FarmProfileDraft {
  const soilOverrides =
    form.includeTexture || form.includePh
      ? {
          known_texture: form.includeTexture
            ? {
                value: form.soilTexture,
                source: form.soilTextureSource,
                observed_or_tested_at: optionalText(form.soilTextureDate),
              }
            : undefined,
          laboratory_ph: form.includePh
            ? {
                value: requiredNumber(form.laboratoryPh),
                tested_at: form.phTestedAt,
                laboratory_name: optionalText(form.laboratoryName),
                report_reference: optionalText(form.reportReference),
              }
            : undefined,
        }
      : undefined;

  return farmProfileDraftSchema.parse({
    location: buildLocation(form),
    planting: buildPlanting(form),
    requested_crop_id: null,
    irrigation: buildIrrigation(form),
    soil_overrides: soilOverrides,
    current_soil_moisture: form.includeMoisture
      ? {
          qualitative: form.soilMoisture,
          source: form.soilMoistureSource,
          notes: optionalText(form.moistureNotes),
        }
      : undefined,
    recent_rainfall: form.includeRainfall
      ? {
          amount_mm: requiredNumber(form.rainfallAmountMm),
          period_days: requiredNumber(form.rainfallPeriodDays),
          period_end_date: optionalText(form.rainfallEndDate),
          source: form.rainfallSource,
        }
      : undefined,
    farmer_goal: form.includeGoal
      ? {
          primary_goal: form.primaryGoal,
          notes: optionalText(form.goalNotes),
        }
      : undefined,
  });
}

function readable(value: string) {
  return value.replaceAll("_", " ").replace(/^\w/, (character) => character.toUpperCase());
}

export function FarmProfileForm() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [step, setStep] = useState(0);
  const [highestStep, setHighestStep] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [locationError, setLocationError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedSessionId, setSavedSessionId] = useState<string | null>(null);

  const latitude = Number(form.latitude);
  const longitude = Number(form.longitude);
  const mapCoordinates =
    Number.isFinite(latitude) && Number.isFinite(longitude) ? { latitude, longitude } : null;

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((current) => ({ ...current, [key]: value }));
    setError(null);
  }

  function setCoordinates(
    coordinates: { latitude: number; longitude: number },
    source: LocationSource,
  ) {
    setForm((current) => ({
      ...current,
      latitude: String(coordinates.latitude),
      longitude: String(coordinates.longitude),
      locationSource: source,
    }));
    setLocationError(null);
    setError(null);
  }

  function loadPlainview() {
    setForm((current) => ({
      ...current,
      farmName: "Plainview demonstration farm",
      locationLabel: "Plainview, Texas",
      latitude: "34.18",
      longitude: "-101.76",
      locationSource: "demo_farm",
    }));
    setLocationError(null);
    setError(null);
  }

  function useCurrentLocation() {
    if (!navigator.geolocation) {
      setLocationError("Current location is not available in this browser.");
      return;
    }

    setLocationError("Requesting your current location...");
    navigator.geolocation.getCurrentPosition(
      (position) => {
        setCoordinates(
          {
            latitude: Number(position.coords.latitude.toFixed(6)),
            longitude: Number(position.coords.longitude.toFixed(6)),
          },
          "gps",
        );
      },
      () => setLocationError("Location permission was not granted. Use the map or coordinates instead."),
      { enableHighAccuracy: true, timeout: 10000 },
    );
  }

  function validateStep(index: number) {
    try {
      if (index === 0) buildLocation(form);
      if (index === 1) buildPlanting(form);
      if (index === 2) buildIrrigation(form);
      if (index >= 3) buildDraft(form);
      setError(null);
      return true;
    } catch (validationError) {
      const message =
        validationError && typeof validationError === "object" && "issues" in validationError
          ? (validationError as { issues: Array<{ message: string }> }).issues[0]?.message
          : null;
      setError(message ?? "Check the highlighted profile information before continuing.");
      return false;
    }
  }

  function nextStep() {
    if (!validateStep(step)) return;
    const next = Math.min(step + 1, steps.length - 1);
    setStep(next);
    setHighestStep((current) => Math.max(current, next));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function previousStep() {
    setError(null);
    setStep((current) => Math.max(current - 1, 0));
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function saveProfile() {
    let draft: FarmProfileDraft;
    try {
      draft = buildDraft(form);
    } catch {
      setError("Review the profile and complete any required values before saving.");
      return;
    }

    setSaving(true);
    setError(null);

    try {
      const response = await fetch("/api/farm-profiles", {
        method: "POST",
        headers: { "content-type": "application/json", accept: "application/json" },
        body: JSON.stringify(draft),
      });
      const result = createFarmProfileResponseSchema.parse(await response.json());

      if (!result.ok) {
        setError(result.error.message);
        return;
      }

      setSavedSessionId(result.assessmentSessionId);
    } catch {
      setError("The farm profile could not be saved. Please try again.");
    } finally {
      setSaving(false);
    }
  }

  if (savedSessionId) {
    return (
      <main className="workspace setup-complete-workspace">
        <section className="setup-complete" aria-labelledby="profile-saved-heading">
          <span className="complete-icon" aria-hidden="true"><Check size={28} /></span>
          <p className="eyebrow">Profile ready</p>
          <h1 id="profile-saved-heading">Farm profile saved</h1>
          <p>Your location and farm inputs are ready for evidence collection.</p>
          <dl className="saved-summary">
            <div><dt>Farm</dt><dd>{form.farmName || form.locationLabel || "Selected farm"}</dd></div>
            <div><dt>Planting</dt><dd>{form.plantingMode === "month" ? form.plannedMonth : form.plannedDate}</dd></div>
            <div><dt>Assessment</dt><dd>{savedSessionId.slice(0, 8).toUpperCase()}</dd></div>
          </dl>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => {
              setForm(initialForm);
              setStep(0);
              setHighestStep(0);
              setSavedSessionId(null);
            }}
          >
            <MapPinned size={17} aria-hidden="true" />
            Add another farm
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="workspace">
      <header className="page-heading">
        <div>
          <p className="eyebrow">New assessment</p>
          <h1>Farm profile</h1>
          <p>Enter the farm location and planting plan. Add field evidence when you have it.</p>
        </div>
        <span className="scope-label">Texas MVP</span>
      </header>

      <ol className="setup-steps" aria-label="Farm profile progress">
        {steps.map((item, index) => {
          const Icon = item.icon;
          const complete = index < step;
          return (
            <li
              className={`setup-step${index === step ? " setup-step-active" : ""}${complete ? " setup-step-complete" : ""}`}
              key={item.label}
            >
              <button
                type="button"
                disabled={index > highestStep}
                aria-current={index === step ? "step" : undefined}
                onClick={() => {
                  setError(null);
                  setStep(index);
                }}
              >
                <span className="step-index" aria-hidden="true">
                  {complete ? <Check size={14} /> : <Icon size={14} />}
                </span>
                <span>{item.label}</span>
              </button>
            </li>
          );
        })}
      </ol>

      <form className="setup-surface" onSubmit={(event) => event.preventDefault()}>
        {step === 0 ? (
          <section aria-labelledby="location-heading">
            <div className="surface-heading">
              <span className="section-icon" aria-hidden="true"><MapPin size={18} /></span>
              <div>
                <h2 id="location-heading">Farm location</h2>
                <p>Coordinates are used for weather, climate and mapped soil evidence.</p>
              </div>
              <span className="required-label">Required</span>
            </div>
            <div className="location-layout">
              <FarmMap
                coordinates={mapCoordinates}
                onChange={(coordinates) => setCoordinates(coordinates, "map_pin")}
              />
              <div className="form-panel">
                <div className="quick-actions">
                  <button className="button button-secondary" type="button" onClick={loadPlainview}>
                    <MapPinned size={17} aria-hidden="true" /> Plainview demo
                  </button>
                  <button className="icon-button" type="button" onClick={useCurrentLocation} title="Use current location" aria-label="Use current location">
                    <LocateFixed size={18} />
                  </button>
                </div>
                {locationError ? <p className="inline-note" role="status">{locationError}</p> : null}
                <label className="field field-full">
                  <span>Farm name <small>Optional</small></span>
                  <input value={form.farmName} maxLength={120} onChange={(event) => update("farmName", event.target.value)} placeholder="e.g. North field" />
                </label>
                <label className="field field-full">
                  <span>Location label <small>Optional</small></span>
                  <input value={form.locationLabel} maxLength={200} onChange={(event) => update("locationLabel", event.target.value)} placeholder="Nearest town or county" />
                </label>
                <div className="field-grid">
                  <label className="field">
                    <span>Latitude</span>
                    <input
                      type="number"
                      min="25.8"
                      max="36.6"
                      step="0.000001"
                      value={form.latitude}
                      onChange={(event) => {
                        update("latitude", event.target.value);
                        update("locationSource", "manual_coordinates");
                      }}
                      required
                    />
                  </label>
                  <label className="field">
                    <span>Longitude</span>
                    <input
                      type="number"
                      min="-106.7"
                      max="-93.4"
                      step="0.000001"
                      value={form.longitude}
                      onChange={(event) => {
                        update("longitude", event.target.value);
                        update("locationSource", "manual_coordinates");
                      }}
                      required
                    />
                  </label>
                </div>
                <p className="field-note">Texas coordinates only. The selected point remains authoritative.</p>
              </div>
            </div>
          </section>
        ) : null}

        {step === 1 ? (
          <section aria-labelledby="planting-heading">
            <div className="surface-heading">
              <span className="section-icon" aria-hidden="true"><CalendarDays size={18} /></span>
              <div><h2 id="planting-heading">Planting plan</h2><p>Choose one planting date or one planning month.</p></div>
              <span className="required-label">Required</span>
            </div>
            <div className="form-body form-body-narrow">
              <fieldset className="field-group">
                <legend>Planning precision</legend>
                <div className="segmented-control">
                  <button type="button" className={form.plantingMode === "month" ? "selected" : ""} aria-pressed={form.plantingMode === "month"} onClick={() => update("plantingMode", "month")}>Planting month</button>
                  <button type="button" className={form.plantingMode === "date" ? "selected" : ""} aria-pressed={form.plantingMode === "date"} onClick={() => update("plantingMode", "date")}>Exact date</button>
                </div>
              </fieldset>
              <div className="field-grid">
                {form.plantingMode === "month" ? (
                  <label className="field"><span>Planned month</span><input type="month" value={form.plannedMonth} onChange={(event) => update("plannedMonth", event.target.value)} required /></label>
                ) : (
                  <label className="field"><span>Planned date</span><input type="date" value={form.plannedDate} onChange={(event) => update("plannedDate", event.target.value)} required /></label>
                )}
                <label className="field"><span>Timing flexibility <small>Days</small></span><input type="number" min="0" max="120" step="1" value={form.flexibilityDays} onChange={(event) => update("flexibilityDays", event.target.value)} /></label>
              </div>
              <p className="field-note">All 22 catalog crops will be compared for this planting period.</p>
            </div>
          </section>
        ) : null}

        {step === 2 ? (
          <section aria-labelledby="water-heading">
            <div className="surface-heading">
              <span className="section-icon" aria-hidden="true"><Droplets size={18} /></span>
              <div><h2 id="water-heading">Water and irrigation</h2><p>Unknown is valid and will reduce confidence instead of counting as a match.</p></div>
              <span className="optional-label">Optional evidence</span>
            </div>
            <div className="form-body">
              <fieldset className="field-group">
                <legend>Is irrigation available?</legend>
                <div className="segmented-control segmented-control-three">
                  {(["yes", "no", "unknown"] as const).map((value) => (
                    <button key={value} type="button" className={form.irrigationAvailability === value ? "selected" : ""} aria-pressed={form.irrigationAvailability === value} onClick={() => update("irrigationAvailability", value)}>{readable(value)}</button>
                  ))}
                </div>
              </fieldset>
              {form.irrigationAvailability === "yes" ? (
                <div className="field-grid field-grid-three">
                  <label className="field"><span>Reliability</span><select value={form.irrigationReliability} onChange={(event) => update("irrigationReliability", event.target.value as FormState["irrigationReliability"])}><option value="reliable">Reliable</option><option value="limited">Limited</option><option value="seasonal">Seasonal</option><option value="unreliable">Unreliable</option><option value="unknown">Unknown</option></select></label>
                  <label className="field"><span>Method</span><select value={form.irrigationMethod} onChange={(event) => update("irrigationMethod", event.target.value as FormState["irrigationMethod"])}><option value="unknown">Unknown</option><option value="drip">Drip</option><option value="center_pivot">Center pivot</option><option value="sprinkler">Sprinkler</option><option value="furrow">Furrow</option><option value="flood">Flood</option><option value="subsurface">Subsurface</option><option value="other">Other</option></select></label>
                  <label className="field"><span>Water source</span><select value={form.waterSource} onChange={(event) => update("waterSource", event.target.value as FormState["waterSource"])}><option value="unknown">Unknown</option><option value="well">Well</option><option value="canal">Canal</option><option value="pond">Pond</option><option value="municipal">Municipal</option><option value="captured_rainwater">Captured rainwater</option><option value="multiple">Multiple</option><option value="other">Other</option></select></label>
                  {form.waterSource === "well" || form.waterSource === "multiple" ? <label className="field"><span>Well capacity <small>gpm, optional</small></span><input type="number" min="0" step="0.1" value={form.wellCapacity} onChange={(event) => update("wellCapacity", event.target.value)} /></label> : null}
                  {form.waterSource === "canal" || form.waterSource === "multiple" ? <><label className="field"><span>Canal allocation <small>Optional</small></span><input type="number" min="0" step="0.1" value={form.canalCapacity} onChange={(event) => update("canalCapacity", event.target.value)} /></label><label className="field"><span>Allocation unit</span><select value={form.canalCapacityUnit} onChange={(event) => update("canalCapacityUnit", event.target.value as FormState["canalCapacityUnit"])}><option value="gpm">gpm</option><option value="cfs">cfs</option><option value="liters_per_second">Liters/second</option><option value="cubic_meters_per_hour">Cubic meters/hour</option><option value="gallons_per_day">Gallons/day</option><option value="acre_feet_per_year">Acre-feet/year</option></select></label></> : null}
                </div>
              ) : null}
              <label className="field field-full"><span>Water notes <small>Optional</small></span><textarea rows={3} maxLength={1000} value={form.irrigationNotes} onChange={(event) => update("irrigationNotes", event.target.value)} placeholder="Known restrictions, seasonal limits or source notes" /></label>
            </div>
          </section>
        ) : null}

        {step === 3 ? (
          <section aria-labelledby="evidence-heading">
            <div className="surface-heading">
              <span className="section-icon" aria-hidden="true"><FlaskConical size={18} /></span>
              <div><h2 id="evidence-heading">Field evidence</h2><p>Add only information you know or have measured.</p></div>
              <span className="optional-label">All optional</span>
            </div>
            <div className="optional-evidence-list">
              <div className="optional-evidence-section">
                <label className="toggle-row"><input type="checkbox" checked={form.includeTexture} onChange={(event) => update("includeTexture", event.target.checked)} /><span><strong>Known soil texture</strong><small>Farmer observation or soil test</small></span></label>
                {form.includeTexture ? <div className="field-grid optional-fields"><label className="field"><span>Texture</span><select value={form.soilTexture} onChange={(event) => update("soilTexture", event.target.value)} required><option value="">Select texture</option><option value="sand">Sand</option><option value="loamy sand">Loamy sand</option><option value="sandy loam">Sandy loam</option><option value="loam">Loam</option><option value="silt loam">Silt loam</option><option value="clay loam">Clay loam</option><option value="clay">Clay</option><option value="other">Other</option></select></label><label className="field"><span>Source</span><select value={form.soilTextureSource} onChange={(event) => update("soilTextureSource", event.target.value as FormState["soilTextureSource"])}><option value="farmer">Farmer observation</option><option value="soil_test_report">Soil test report</option></select></label><label className="field"><span>Observed or tested <small>Optional</small></span><input type="date" value={form.soilTextureDate} onChange={(event) => update("soilTextureDate", event.target.value)} /></label></div> : null}
              </div>
              <div className="optional-evidence-section">
                <label className="toggle-row"><input type="checkbox" checked={form.includePh} onChange={(event) => update("includePh", event.target.checked)} /><span><strong>Laboratory soil pH</strong><small>Use only a laboratory result</small></span></label>
                {form.includePh ? <div className="field-grid optional-fields"><label className="field"><span>pH value</span><input type="number" min="0" max="14" step="0.1" value={form.laboratoryPh} onChange={(event) => update("laboratoryPh", event.target.value)} required /></label><label className="field"><span>Tested date</span><input type="date" value={form.phTestedAt} onChange={(event) => update("phTestedAt", event.target.value)} required /></label><label className="field"><span>Laboratory <small>Optional</small></span><input maxLength={200} value={form.laboratoryName} onChange={(event) => update("laboratoryName", event.target.value)} /></label><label className="field"><span>Report reference <small>Optional</small></span><input maxLength={300} value={form.reportReference} onChange={(event) => update("reportReference", event.target.value)} /></label></div> : null}
              </div>
              <div className="optional-evidence-section">
                <label className="toggle-row"><input type="checkbox" checked={form.includeMoisture} onChange={(event) => update("includeMoisture", event.target.checked)} /><span><strong>Current soil moisture</strong><small>Observation or sensor reading</small></span></label>
                {form.includeMoisture ? <div className="field-grid optional-fields"><label className="field"><span>Condition</span><select value={form.soilMoisture} onChange={(event) => update("soilMoisture", event.target.value as FormState["soilMoisture"])}><option value="very_dry">Very dry</option><option value="dry">Dry</option><option value="adequate">Adequate</option><option value="wet">Wet</option><option value="saturated">Saturated</option><option value="unknown">Unknown</option></select></label><label className="field"><span>Source</span><select value={form.soilMoistureSource} onChange={(event) => update("soilMoistureSource", event.target.value as FormState["soilMoistureSource"])}><option value="farmer_observation">Farmer observation</option><option value="sensor">Sensor</option><option value="other">Other</option><option value="unknown">Unknown</option></select></label><label className="field field-full"><span>Moisture notes <small>Optional</small></span><textarea rows={2} maxLength={1000} value={form.moistureNotes} onChange={(event) => update("moistureNotes", event.target.value)} /></label></div> : null}
              </div>
              <div className="optional-evidence-section">
                <label className="toggle-row"><input type="checkbox" checked={form.includeRainfall} onChange={(event) => update("includeRainfall", event.target.checked)} /><span><strong>Recent farm rainfall</strong><small>Farmer record or farm rain gauge</small></span></label>
                {form.includeRainfall ? <div className="field-grid optional-fields"><label className="field"><span>Amount <small>mm</small></span><input type="number" min="0" step="0.1" value={form.rainfallAmountMm} onChange={(event) => update("rainfallAmountMm", event.target.value)} required /></label><label className="field"><span>Period <small>Days</small></span><input type="number" min="1" max="90" step="1" value={form.rainfallPeriodDays} onChange={(event) => update("rainfallPeriodDays", event.target.value)} required /></label><label className="field"><span>Period end <small>Optional</small></span><input type="date" value={form.rainfallEndDate} onChange={(event) => update("rainfallEndDate", event.target.value)} /></label><label className="field"><span>Source</span><select value={form.rainfallSource} onChange={(event) => update("rainfallSource", event.target.value as FormState["rainfallSource"])}><option value="farmer">Farmer record</option><option value="farm_rain_gauge">Farm rain gauge</option></select></label></div> : null}
              </div>
              <div className="optional-evidence-section">
                <label className="toggle-row"><input type="checkbox" checked={form.includeGoal} onChange={(event) => update("includeGoal", event.target.checked)} /><span><strong>Farm goal</strong><small>Used to explain and compare suitable options</small></span></label>
                {form.includeGoal ? <div className="field-grid optional-fields"><label className="field"><span>Primary goal</span><select value={form.primaryGoal} onChange={(event) => update("primaryGoal", event.target.value as FormState["primaryGoal"])}><option value="maximize_yield">Maximize yield potential</option><option value="reduce_water_use">Reduce water use</option><option value="heat_resilience">Heat resilience</option><option value="lower_input_cost">Lower input cost</option><option value="market_crop">Market crop</option><option value="household_use">Household use</option><option value="soil_health">Soil health</option><option value="other">Other</option></select></label><label className="field field-full"><span>Goal notes <small>Optional</small></span><textarea rows={3} maxLength={1500} value={form.goalNotes} onChange={(event) => update("goalNotes", event.target.value)} /></label></div> : null}
              </div>
            </div>
          </section>
        ) : null}

        {step === 4 ? (
          <section aria-labelledby="review-heading">
            <div className="surface-heading">
              <span className="section-icon" aria-hidden="true"><ClipboardCheck size={18} /></span>
              <div><h2 id="review-heading">Review farm profile</h2><p>Confirm the inputs that will be stored with this assessment.</p></div>
            </div>
            <div className="review-list">
              <div className="review-section"><div><h3>Location</h3><p>{form.farmName || form.locationLabel || "Selected farm point"}</p><span>{form.latitude}, {form.longitude}</span></div><button className="icon-button" type="button" onClick={() => setStep(0)} aria-label="Edit location" title="Edit location"><Pencil size={17} /></button></div>
              <div className="review-section"><div><h3>Planting plan</h3><p>{form.plantingMode === "month" ? form.plannedMonth : form.plannedDate}</p><span>{form.flexibilityDays ? `${form.flexibilityDays} days flexibility` : "No timing flexibility supplied"}</span></div><button className="icon-button" type="button" onClick={() => setStep(1)} aria-label="Edit planting plan" title="Edit planting plan"><Pencil size={17} /></button></div>
              <div className="review-section"><div><h3>Water</h3><p>Irrigation: {readable(form.irrigationAvailability)}</p><span>{form.irrigationAvailability === "yes" ? `${readable(form.irrigationReliability)} · ${readable(form.waterSource)}` : "No additional water details"}</span></div><button className="icon-button" type="button" onClick={() => setStep(2)} aria-label="Edit water inputs" title="Edit water inputs"><Pencil size={17} /></button></div>
              <div className="review-section"><div><h3>Field evidence</h3><p>{[form.includeTexture, form.includePh, form.includeMoisture, form.includeRainfall, form.includeGoal].filter(Boolean).length} optional items supplied</p><span>Missing optional evidence will remain unknown.</span></div><button className="icon-button" type="button" onClick={() => setStep(3)} aria-label="Edit field evidence" title="Edit field evidence"><Pencil size={17} /></button></div>
            </div>
            <div className="review-notice"><Check size={17} aria-hidden="true" /><span>This assessment ranks all 22 catalog crops for preliminary suitability. It does not predict yield or prescribe irrigation.</span></div>
          </section>
        ) : null}

        {error ? <div className="form-error" role="alert">{error}</div> : null}

        <footer className="form-actions">
          <button className="button button-secondary" type="button" onClick={previousStep} disabled={step === 0 || saving}><ArrowLeft size={17} aria-hidden="true" /> Back</button>
          <span>Step {step + 1} of {steps.length}</span>
          {step < steps.length - 1 ? <button className="button button-primary" type="button" onClick={nextStep}>Continue <ArrowRight size={17} aria-hidden="true" /></button> : <button className="button button-primary" type="button" onClick={saveProfile} disabled={saving}>{saving ? <LoaderCircle className="spin" size={17} aria-hidden="true" /> : <Save size={17} aria-hidden="true" />}{saving ? "Saving..." : "Save farm profile"}</button>}
        </footer>
      </form>
    </main>
  );
}
