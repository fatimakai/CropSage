"use client";

import {
  AlertTriangle,
  ArrowLeft,
  CalendarDays,
  Check,
  ChevronRight,
  CircleGauge,
  Droplets,
  GitCompareArrows,
  Info,
  LoaderCircle,
  RotateCcw,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import {
  scenarioDraftSchema,
  type FarmProfileSnapshot,
  type RecommendationOutput,
  type ScenarioDraft,
  type ScenarioType,
} from "@/lib/contracts";
import { formatScore, titleCaseIdentifier } from "@/lib/recommendations/presentation";

type ScenarioComparisonProps = {
  assessmentSessionId: string;
  baseline: RecommendationOutput;
  profile: FarmProfileSnapshot;
};

const assumptions = [
  "The farm location and crop catalog version remain unchanged.",
  "Date-aligned provider evidence must be refreshed before scenario scores can render.",
  "The result remains preliminary suitability, not a yield or irrigation prescription.",
] as const;

const scenarioTypes: Array<{ id: ScenarioType; label: string; description: string; icon: typeof CalendarDays }> = [
  { id: "planting_timing", label: "Planting timing", description: "Change planting month or flexibility.", icon: CalendarDays },
  { id: "irrigation_access", label: "Irrigation access", description: "Change availability or reliability.", icon: Droplets },
  { id: "combined", label: "Combined", description: "Change both supported input groups.", icon: GitCompareArrows },
];

export function ScenarioComparison({ assessmentSessionId, baseline, profile }: ScenarioComparisonProps) {
  const baselineMonth = profile.planting.planned_month ?? profile.planting.planned_date?.slice(0, 7) ?? "2026-08";
  const [scenarioType, setScenarioType] = useState<ScenarioType>("planting_timing");
  const [plannedMonth, setPlannedMonth] = useState(baselineMonth === "2026-12" ? "2027-01" : `${baselineMonth.slice(0, 5)}${String(Number(baselineMonth.slice(5)) + 1).padStart(2, "0")}`);
  const [flexibilityDays, setFlexibilityDays] = useState(profile.planting.flexibility_days ?? 30);
  const [irrigationAvailability, setIrrigationAvailability] = useState<"yes" | "no" | "unknown">(profile.irrigation?.availability === "yes" ? "no" : "yes");
  const [irrigationReliability, setIrrigationReliability] = useState<"reliable" | "limited" | "seasonal" | "unreliable" | "unknown" | "not_applicable">("limited");
  const [acceptedAssumptions, setAcceptedAssumptions] = useState<boolean[]>([false, false, false]);
  const [prepared, setPrepared] = useState<ScenarioDraft | null>(null);
  const [error, setError] = useState<string | null>(null);

  const baselineEligible = useMemo(() => baseline.rankings.filter((crop) => crop.regionally_eligible), [baseline]);

  function buildDraft(): ScenarioDraft | null {
    const changes: ScenarioDraft["changes"] = {};
    if (scenarioType !== "irrigation_access") {
      if (plannedMonth !== baselineMonth) changes.planned_month = plannedMonth;
      if (flexibilityDays !== (profile.planting.flexibility_days ?? 30)) changes.planting_flexibility_days = flexibilityDays;
    }
    if (scenarioType !== "planting_timing") {
      if (irrigationAvailability !== profile.irrigation?.availability) changes.irrigation_availability = irrigationAvailability;
      if (irrigationReliability !== profile.irrigation?.reliability) changes.irrigation_reliability = irrigationReliability;
    }

    const parsed = scenarioDraftSchema.safeParse({
      scenario_type: scenarioType,
      changes,
      assumptions: assumptions.filter((_, index) => acceptedAssumptions[index]),
    });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "The scenario is incomplete.");
      return null;
    }
    return parsed.data;
  }

  function prepareScenario() {
    const draft = buildDraft();
    if (!draft) return;
    setPrepared(draft);
    setError(null);
  }

  function resetScenario() {
    setPrepared(null);
    setError(null);
  }

  return (
    <main className="workspace scenario-workspace">
      <nav className="context-navigation" aria-label="Assessment navigation"><Link href={`/assessments/${assessmentSessionId}/results`}><ArrowLeft size={16} aria-hidden="true" />Recommendation results</Link></nav>

      <header className="page-heading scenario-heading">
        <div><p className="eyebrow">Preliminary suitability</p><h1>Scenario comparison</h1><p>Prepare supported farm-input changes against the validated baseline run.</p></div>
        <span className="validation-badge"><ShieldCheck size={17} aria-hidden="true" /><span>Baseline validated<small>{baseline.scoring_version}</small></span></span>
      </header>

      <section className="scenario-baseline" aria-labelledby="baseline-heading">
        <div><h2 id="baseline-heading">Baseline context</h2><p>{baseline.location.farm_name} · {titleCaseIdentifier(baseline.location.texas_region_id)} region</p></div>
        <dl>
          <div><dt>Planting plan</dt><dd>{baselineMonth}</dd></div>
          <div><dt>Flexibility</dt><dd>{profile.planting.flexibility_days ?? "Unknown"} days</dd></div>
          <div><dt>Irrigation</dt><dd>{profile.irrigation ? `${titleCaseIdentifier(profile.irrigation.availability)} · ${titleCaseIdentifier(profile.irrigation.reliability ?? "unknown")}` : "Unknown"}</dd></div>
          <div><dt>Eligible crops</dt><dd>{baselineEligible.length} of 22</dd></div>
        </dl>
      </section>

      {!prepared ? (
        <div className="scenario-builder-layout">
          <section className="scenario-builder" aria-labelledby="scenario-builder-heading">
            <div className="section-title-row"><div><h2 id="scenario-builder-heading">Scenario inputs</h2><p>Only fields already supported by the farm profile and engine contract are available.</p></div><GitCompareArrows size={20} aria-hidden="true" /></div>
            <fieldset className="scenario-type-fieldset"><legend>Change type</legend><div className="scenario-type-grid">{scenarioTypes.map((option) => { const Icon=option.icon; return <button type="button" className={scenarioType === option.id ? "scenario-type selected" : "scenario-type"} onClick={() => setScenarioType(option.id)} key={option.id}><Icon size={18} aria-hidden="true" /><span><strong>{option.label}</strong><small>{option.description}</small></span>{scenarioType === option.id ? <Check size={17} aria-hidden="true" /> : null}</button>; })}</div></fieldset>

            {scenarioType !== "irrigation_access" ? <div className="scenario-input-section"><h3><CalendarDays size={17} aria-hidden="true" />Planting timing</h3><div className="field-grid"><label className="field">Planned month<input type="month" value={plannedMonth} onChange={(event) => setPlannedMonth(event.target.value)} /></label><label className="field">Flexibility days<input type="number" min={0} max={120} value={flexibilityDays} onChange={(event) => setFlexibilityDays(Number(event.target.value))} /></label></div></div> : null}

            {scenarioType !== "planting_timing" ? <div className="scenario-input-section"><h3><Droplets size={17} aria-hidden="true" />Irrigation evidence</h3><div className="field-grid"><label className="field">Availability<select value={irrigationAvailability} onChange={(event) => setIrrigationAvailability(event.target.value as typeof irrigationAvailability)}><option value="yes">Available</option><option value="no">Not available</option><option value="unknown">Unknown</option></select></label><label className="field">Reliability<select value={irrigationReliability} onChange={(event) => setIrrigationReliability(event.target.value as typeof irrigationReliability)}><option value="reliable">Reliable</option><option value="limited">Limited</option><option value="seasonal">Seasonal</option><option value="unreliable">Unreliable</option><option value="unknown">Unknown</option><option value="not_applicable">Not applicable</option></select></label></div></div> : null}
          </section>

          <aside className="scenario-assumptions"><h2>Confirm assumptions</h2><p>Scenario results can only be compared when their unchanged context is explicit.</p><div>{assumptions.map((assumption, index) => <label key={assumption}><input type="checkbox" checked={acceptedAssumptions[index]} onChange={(event) => setAcceptedAssumptions((current) => current.map((value, itemIndex) => itemIndex === index ? event.target.checked : value))} /><span>{assumption}</span></label>)}</div>{error ? <p className="scenario-error" role="alert"><AlertTriangle size={15} aria-hidden="true" />{error}</p> : null}<button className="button button-primary" type="button" onClick={prepareScenario}>Prepare comparison<ChevronRight size={17} aria-hidden="true" /></button></aside>
        </div>
      ) : (
        <>
          <section className="scenario-prepared-status" aria-live="polite"><span><LoaderCircle className="spin" size={21} aria-hidden="true" /></span><div><h2>Scenario prepared, scoring pending</h2><p>The supported changes and assumptions are ready for a scenario run. Scores remain hidden until Group 7 sends this contract to the Python engine, persists the child run, and receives validator authorization.</p></div><button className="button button-secondary" type="button" onClick={resetScenario}><RotateCcw size={16} aria-hidden="true" />Change inputs</button></section>

          <section className="scenario-change-summary" aria-labelledby="change-summary-heading"><div className="section-title-row"><div><h2 id="change-summary-heading">Confirmed changes</h2><p>Parent context: baseline assessment {assessmentSessionId.slice(0, 8).toUpperCase()}</p></div></div><dl>{Object.entries(prepared.changes).map(([key,value]) => <div key={key}><dt>{titleCaseIdentifier(key)}</dt><dd>{titleCaseIdentifier(String(value))}</dd></div>)}</dl><div className="confirmed-assumptions"><h3>Unchanged assumptions</h3><ul>{prepared.assumptions.map((assumption) => <li key={assumption}><Check size={14} aria-hidden="true" />{assumption}</li>)}</ul></div></section>

          <section className="scenario-delta-section" aria-labelledby="scenario-delta-heading"><div className="section-title-row"><div><h2 id="scenario-delta-heading">Baseline versus scenario</h2><p>Baseline values remain visible. Scenario values and deltas are unavailable until a validated child run exists.</p></div><CircleGauge size={20} aria-hidden="true" /></div><div className="scenario-table-wrap"><table className="scenario-table"><thead><tr><th>Crop</th><th>Baseline rank</th><th>Baseline suitability</th><th>Scenario rank</th><th>Rank delta</th><th>Score delta</th></tr></thead><tbody>{baseline.rankings.map((crop) => <tr key={crop.crop_id}><td><Link href={`/assessments/${assessmentSessionId}/crops/${crop.crop_id}`}>{crop.crop_name}</Link><span>{crop.regionally_eligible ? `Eligible rank ${crop.eligible_rank}` : "Regionally unsupported"}</span></td><td>{crop.overall_rank}</td><td>{formatScore(crop.suitability_score)}{crop.suitability_score === null ? "" : "/100"}</td><td><span className="pending-value">Pending</span></td><td><span className="pending-value">Pending</span></td><td><span className="pending-value">Pending</span></td></tr>)}</tbody></table></div></section>
        </>
      )}

      <section className="scenario-boundary-note"><Info size={17} aria-hidden="true" /><p>CropSage does not estimate scenario deltas in the browser. Only values returned by the deterministic engine and authorized by validation can replace the pending state.</p></section>
    </main>
  );
}
