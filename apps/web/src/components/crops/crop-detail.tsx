import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  CheckCircle2,
  CircleHelp,
  Clock3,
  Database,
  ExternalLink,
  FlaskConical,
  Gauge,
  MapPin,
  ShieldCheck,
  Sprout,
} from "lucide-react";
import Link from "next/link";

import type { CropScoreResult, ScoreFactor } from "@/lib/contracts";
import type {
  PreparedCropDetail,
  RequirementEvidenceRow,
} from "@/lib/crops/prepared-crop-details";
import { formatScore, titleCaseIdentifier } from "@/lib/recommendations/presentation";

type CropDetailProps = {
  assessmentSessionId: string;
  detail: PreparedCropDetail;
};

function guidanceLabel(crop: CropScoreResult) {
  if (crop.recommendation === "recommended") return "Consider";
  if (crop.recommendation === "conditional") return "Consider with conditions";
  if (crop.recommendation === "not_recommended") return "Not preferred now";
  return "Evidence incomplete";
}

function FactorAvailability({ factor }: { factor: ScoreFactor }) {
  if (!factor.available) {
    return <span className="factor-availability factor-unavailable"><CircleHelp size={13} aria-hidden="true" />Unknown</span>;
  }
  if (factor.scoring_use !== "scored") {
    return <span className="factor-availability factor-information"><CircleHelp size={13} aria-hidden="true" />Information only</span>;
  }
  return <span className="factor-availability factor-scored"><CheckCircle2 size={13} aria-hidden="true" />Scored</span>;
}

function ComparisonStatus({ row }: { row: RequirementEvidenceRow }) {
  const labels = {
    strong: "Strong fit",
    mixed: "Partial fit",
    weak: "Weak fit",
    unknown: "Unknown",
  };
  return <span className={`comparison-status comparison-${row.status}`}>{labels[row.status]}</span>;
}

function FactorTable({ factors }: { factors: ScoreFactor[] }) {
  return (
    <div className="factor-table-wrap">
      <table className="factor-table">
        <thead><tr><th>Factor</th><th>Category</th><th>Weight</th><th>Score</th><th>Use</th><th>Reason</th><th>Sources</th></tr></thead>
        <tbody>
          {factors.map((factor) => (
            <tr key={factor.factor_id}>
              <td><strong>{titleCaseIdentifier(factor.factor_id)}</strong></td>
              <td>{titleCaseIdentifier(factor.category)}</td>
              <td>{factor.weight_percent}%</td>
              <td>{factor.score === null ? "Unknown" : `${formatScore(factor.score)}/100`}</td>
              <td><FactorAvailability factor={factor} /></td>
              <td><p>{factor.reason}</p></td>
              <td>{factor.evidence.sources.length ? factor.evidence.sources.map(titleCaseIdentifier).join(", ") : "None"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function CropDetail({ assessmentSessionId, detail }: CropDetailProps) {
  const { crop, catalog, comparisons, providers, references } = detail;
  const regional = catalog.regional_suitability.find((item) => item.region_id === "plains");
  const planting = catalog.planting_windows_by_region.find((item) => item.region_id === "plains");

  return (
    <main className="workspace crop-detail-workspace">
      <nav className="context-navigation" aria-label="Assessment navigation">
        <Link href={`/assessments/${assessmentSessionId}/results`}><ArrowLeft size={16} aria-hidden="true" />All recommendations</Link>
        <Link href={`/assessments/${assessmentSessionId}/scenarios`}>Compare scenarios<ArrowRight size={16} aria-hidden="true" /></Link>
      </nav>

      <header className="crop-detail-heading">
        <div className="crop-heading-icon"><Sprout size={24} aria-hidden="true" /></div>
        <div>
          <p className="eyebrow">Eligible rank {crop.eligible_rank ?? "not assigned"} · Overall rank {crop.overall_rank}</p>
          <h1>{crop.crop_name}</h1>
          <p><em>{catalog.scientific_name}</em> · {catalog.production_use}</p>
        </div>
        <span className={`recommendation-tag recommendation-${crop.recommendation}`}>{guidanceLabel(crop)}</span>
      </header>

      <section className="crop-score-band" aria-label="Crop score summary">
        <div><span>Suitability</span><strong>{formatScore(crop.suitability_score)}{crop.suitability_score === null ? "" : "/100"}</strong><small>Preliminary fit</small></div>
        <div><span>Confidence</span><strong>{formatScore(crop.confidence_score)}{crop.confidence_score === null ? "" : "/100"}</strong><small>{crop.confidence_band ? titleCaseIdentifier(crop.confidence_band) : "Unknown"} confidence</small></div>
        <div><span>Evidence coverage</span><strong>{formatScore(crop.evidence_coverage_percent)}{crop.evidence_coverage_percent === null ? "" : "%"}</strong><small>Available engine evidence</small></div>
        <div><span>Regional status</span><strong>{crop.regionally_eligible ? "Eligible" : "Unsupported"}</strong><small>Texas Plains catalog rule</small></div>
      </section>

      <div className="crop-detail-layout">
        <div className="crop-detail-main">
          <section aria-labelledby="comparison-heading">
            <div className="section-title-row"><div><h2 id="comparison-heading">Requirements versus evidence</h2><p>Stable catalog requirements compared with the evidence used by the engine.</p></div><Gauge size={20} aria-hidden="true" /></div>
            <div className="requirement-comparison-list">
              {comparisons.map((row) => (
                <article className="requirement-comparison" key={row.id}>
                  <header><h3>{row.requirement}</h3><ComparisonStatus row={row} /></header>
                  <div className="comparison-values">
                    <div><span>Crop requirement</span><strong>{row.catalogValue}</strong></div>
                    <div><span>Location evidence</span><strong>{row.locationValue}</strong></div>
                    <div><span>Factor score</span><strong>{row.factorScore === null ? "Unknown" : `${formatScore(row.factorScore)}/100`}</strong></div>
                  </div>
                  <p>{row.note}</p>
                  <small>Sources: {row.sources.length ? row.sources.map(titleCaseIdentifier).join(", ") : "No active source"}</small>
                </article>
              ))}
            </div>
          </section>

          <section className="factor-section" aria-labelledby="factor-heading">
            <div className="section-title-row"><div><h2 id="factor-heading">Deterministic factor breakdown</h2><p>These are engine outputs. CropSage does not recalculate them in the browser.</p></div><FlaskConical size={20} aria-hidden="true" /></div>
            <FactorTable factors={crop.factors} />
          </section>

          <section className="provider-evidence-section" aria-labelledby="provider-evidence-heading">
            <div className="section-title-row"><div><h2 id="provider-evidence-heading">Evidence provenance</h2><p>Sanitized metadata from the prepared evidence bundle.</p></div><Database size={20} aria-hidden="true" /></div>
            <div className="provider-evidence-list">
              {providers.map((provider) => (
                <article key={provider.id}>
                  <header><h3>{provider.name}</h3><span className="source-mode source-cache">Prepared artifact</span></header>
                  <p>{provider.role}</p>
                  <dl>
                    <div><dt>Generated</dt><dd>{new Date(provider.generatedAt).toLocaleString("en-US", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" })} UTC</dd></div>
                    <div><dt>Freshness at validation</dt><dd>{titleCaseIdentifier(provider.freshnessStatus)} · {provider.ageHours.toFixed(1)} hours old</dd></div>
                    <div><dt>Data vintage</dt><dd>{provider.sourceDataVintage}</dd></div>
                    <div><dt>Spatial resolution</dt><dd>{provider.spatialResolution}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          </section>
        </div>

        <aside className="crop-profile-sidebar" aria-label="Crop catalog profile">
          <section>
            <h2>Catalog profile</h2>
            <dl className="catalog-profile-list">
              <div><dt>Texas Plains rating</dt><dd>{regional ? titleCaseIdentifier(regional.rating) : "Not supported"}</dd></div>
              <div><dt>Planting windows</dt><dd>{planting?.windows.join(", ") ?? "Unknown"}</dd></div>
              <div><dt>Days to maturity</dt><dd>{catalog.days_to_maturity.min}-{catalog.days_to_maturity.max} days</dd></div>
              <div><dt>Drought tolerance</dt><dd>{titleCaseIdentifier(catalog.drought_tolerance)}</dd></div>
              <div><dt>Root-zone depth</dt><dd>{catalog.effective_root_zone_depth_cm.min}-{catalog.effective_root_zone_depth_cm.max} cm</dd></div>
              <div><dt>Catalog confidence</dt><dd>{titleCaseIdentifier(catalog.confidence)}</dd></div>
              <div><dt>Record status</dt><dd>{titleCaseIdentifier(catalog.record_status)}</dd></div>
              <div><dt>Last reviewed</dt><dd>{catalog.last_reviewed}</dd></div>
            </dl>
          </section>

          <section className="crop-risk-summary">
            <h2><AlertTriangle size={17} aria-hidden="true" />Key risks</h2>
            <ul>{crop.key_risks.map((risk) => <li key={risk.factor_id}><strong>{titleCaseIdentifier(risk.factor_id)}</strong><span>{risk.reason}</span></li>)}</ul>
          </section>

          <section className="crop-strength-summary">
            <h2><ShieldCheck size={17} aria-hidden="true" />Strongest signals</h2>
            <ul>{crop.key_strengths.map((strength) => <li key={strength.factor_id}><strong>{titleCaseIdentifier(strength.factor_id)}</strong><span>{strength.reason}</span></li>)}</ul>
          </section>

          {crop.warnings.length ? <section className="crop-warning-summary"><h2><Clock3 size={17} aria-hidden="true" />Warnings</h2><ul>{crop.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul></section> : null}
        </aside>
      </div>

      <section className="catalog-notes" aria-labelledby="catalog-notes-heading">
        <div><BookOpen size={19} aria-hidden="true" /><h2 id="catalog-notes-heading">Catalog assumptions and references</h2></div>
        <p>{catalog.variety_scope}</p>
        <ul className="assumption-list">{catalog.assumptions.map((assumption) => <li key={assumption}>{assumption}</li>)}</ul>
        <div className="reference-list">
          {references.map((reference) => (
            <a href={reference.url} target="_blank" rel="noreferrer" key={reference.source_id}><span>{reference.source_id}</span><strong>{reference.title}</strong><small>{reference.publisher}</small><ExternalLink size={14} aria-hidden="true" /></a>
          ))}
        </div>
      </section>

      <section className="crop-detail-disclaimer"><MapPin size={17} aria-hidden="true" /><p>This detail explains the validated Plainview demonstration result. It is preliminary suitability, not a yield guarantee, planting instruction, or irrigation prescription.</p></section>
    </main>
  );
}
