import {
  AlertTriangle,
  ArrowLeft,
  BarChart3,
  CheckCircle2,
  ChevronRight,
  CircleGauge,
  Info,
  MapPin,
  ShieldCheck,
  ShieldX,
  Sprout,
} from "lucide-react";
import Link from "next/link";

import type { CropScoreResult, ScoreExplanation } from "@/lib/contracts";
import {
  formatScore,
  groupRecommendationRankings,
  titleCaseIdentifier,
  type PreparedRecommendationResult,
} from "@/lib/recommendations/presentation";

type RecommendationResultsProps = {
  assessmentSessionId: string;
  result: PreparedRecommendationResult;
};

function FactorSummary({ item }: { item: ScoreExplanation }) {
  return (
    <li>
      <span>{titleCaseIdentifier(item.factor_id)}</span>
      <p>{item.reason}</p>
    </li>
  );
}

function ScoreValue({ value }: { value: number | null }) {
  return (
    <span className={value === null ? "metric-value metric-unknown" : "metric-value"}>
      {formatScore(value)}
      {value === null ? null : <small>/100</small>}
    </span>
  );
}

function TopCrop({
  crop,
  assessmentSessionId,
  showRank = true,
}: {
  crop: CropScoreResult;
  assessmentSessionId: string;
  showRank?: boolean;
}) {
  return (
    <article className="top-crop-card">
      <header className={showRank ? undefined : "selected-crop-header"}>
        {showRank ? (
          <span className="rank-number" aria-label={`Eligible rank ${crop.eligible_rank}`}>
            {crop.eligible_rank}
          </span>
        ) : null}
        <div>
          <h3>{crop.crop_name}</h3>
        </div>
      </header>

      <div className="top-crop-metrics">
        <div>
          <span>Suitability</span>
          <ScoreValue value={crop.suitability_score} />
        </div>
        <div>
          <span>Confidence</span>
          <ScoreValue value={crop.confidence_score} />
          <small>{crop.confidence_band ? titleCaseIdentifier(crop.confidence_band) : "Unknown"}</small>
        </div>
      </div>

      <details className="crop-evidence-details">
        <summary>
          Evidence summary <ChevronRight size={15} aria-hidden="true" />
        </summary>
        <div className="evidence-columns">
          <div>
            <h4>Strongest signals</h4>
            <ul>{crop.key_strengths.map((item) => <FactorSummary item={item} key={item.factor_id} />)}</ul>
          </div>
          <div>
            <h4>Risk signals</h4>
            <ul>{crop.key_risks.map((item) => <FactorSummary item={item} key={item.factor_id} />)}</ul>
          </div>
        </div>
      </details>
      <Link className="top-crop-detail-link" href={`/assessments/${assessmentSessionId}/crops/${crop.crop_id}`}>View crop evidence <ChevronRight size={15} aria-hidden="true" /></Link>
    </article>
  );
}

function EligibleTable({ crops, assessmentSessionId }: { crops: CropScoreResult[]; assessmentSessionId: string }) {
  return (
    <>
      <div className="ranking-table-wrap">
        <table className="ranking-table">
          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Crop</th>
              <th scope="col">Suitability</th>
              <th scope="col">Confidence</th>
            </tr>
          </thead>
          <tbody>
            {crops.map((crop) => (
              <tr key={crop.crop_id}>
                <td><strong>{crop.eligible_rank}</strong></td>
                <td><Link className="ranking-crop-link" href={`/assessments/${assessmentSessionId}/crops/${crop.crop_id}`}>{crop.crop_name}<ChevronRight size={13} aria-hidden="true" /></Link><span>{crop.crop_id}</span></td>
                <td><ScoreValue value={crop.suitability_score} /></td>
                <td><ScoreValue value={crop.confidence_score} /><span>{crop.confidence_band ? titleCaseIdentifier(crop.confidence_band) : "Unknown"}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ol className="ranking-mobile-list">
        {crops.map((crop) => (
          <li key={crop.crop_id}>
            <div className="mobile-rank-heading">
              <span className="rank-number">{crop.eligible_rank}</span>
              <div><Link className="ranking-crop-link" href={`/assessments/${assessmentSessionId}/crops/${crop.crop_id}`}>{crop.crop_name}<ChevronRight size={13} aria-hidden="true" /></Link></div>
            </div>
            <dl>
              <div><dt>Suitability</dt><dd>{formatScore(crop.suitability_score)}{crop.suitability_score === null ? "" : "/100"}</dd></div>
              <div><dt>Confidence</dt><dd>{formatScore(crop.confidence_score)}{crop.confidence_score === null ? "" : "/100"} · {crop.confidence_band ? titleCaseIdentifier(crop.confidence_band) : "Unknown"}</dd></div>
            </dl>
          </li>
        ))}
      </ol>
    </>
  );
}

function BlockedResult({ assessmentSessionId, result }: RecommendationResultsProps) {
  if (result.state !== "blocked") return null;

  return (
    <main className="workspace results-workspace blocked-results">
      <section className="blocked-result-panel" role="alert">
        <span className="blocked-result-icon"><ShieldX size={28} aria-hidden="true" /></span>
        <p className="eyebrow">Preliminary suitability</p>
        <h1>Results are not ready to display</h1>
        <p>The validator has not authorized this recommendation. Scores and rankings remain hidden so an incomplete result cannot be mistaken for a valid assessment.</p>
        {result.validation.errors.length > 0 ? <ul>{result.validation.errors.map((error) => <li key={error}>{error}</li>)}</ul> : null}
        <Link className="button button-secondary" href={`/assessments/${assessmentSessionId}/progress`}><ArrowLeft size={17} aria-hidden="true" />Return to analysis</Link>
      </section>
    </main>
  );
}

export function RecommendationResults(props: RecommendationResultsProps) {
  const { assessmentSessionId, result } = props;

  if (result.state === "blocked") {
    return <BlockedResult {...props} />;
  }

  const { recommendation, validation } = result;
  const groups = groupRecommendationRankings(recommendation.rankings);
  const location = recommendation.location;
  const isRequestedCropAssessment = recommendation.requested_crop_id !== null;
  const requestedCrop = isRequestedCropAssessment
    ? recommendation.requested_crop_result
      ?? recommendation.rankings.find(
        (crop) => crop.crop_id === recommendation.requested_crop_id,
      )
      ?? null
    : null;
  const requestedCropName = requestedCrop?.crop_name
    ?? (recommendation.requested_crop_id
      ? titleCaseIdentifier(recommendation.requested_crop_id)
      : null);

  return (
    <main className="workspace results-workspace">
      <header className="page-heading results-heading">
        <div>
          <p className="eyebrow">Preliminary suitability</p>
          <h1>{isRequestedCropAssessment ? "Crop assessment" : "Crop recommendations"}</h1>
          <p className="results-location"><MapPin size={15} aria-hidden="true" />{location.farm_name} · {titleCaseIdentifier(location.texas_region_id)} region</p>
        </div>
        <div className="validation-badge"><ShieldCheck size={17} aria-hidden="true" /><span>Validated for display<small>{validation.validator_version}</small></span></div>
      </header>

      <section className="results-context" aria-label="Assessment summary">
        <div><span>Assessment</span><strong>{assessmentSessionId.slice(0, 8).toUpperCase()}</strong></div>
        <div><span>{isRequestedCropAssessment ? "Crop assessed" : "Catalog results"}</span><strong>{isRequestedCropAssessment ? requestedCropName : `${recommendation.rankings.length} crops`}</strong></div>
        <div><span>{isRequestedCropAssessment ? "Regional support" : "Regionally eligible"}</span><strong>{isRequestedCropAssessment ? requestedCrop?.regionally_eligible ? "Supported" : "Not supported" : `${groups.eligible.length} crops`}</strong></div>
        <div><span>Evaluation</span><strong>{titleCaseIdentifier(recommendation.evaluation_mode)}</strong></div>
      </section>

      {isRequestedCropAssessment ? (
        <section className="top-results-section" aria-labelledby="selected-crop-heading">
          <div className="section-title-row results-section-title">
            <div><h2 id="selected-crop-heading">Selected crop result</h2><p>{requestedCropName} assessed for this farm and planting plan.</p></div>
            <CircleGauge size={20} aria-hidden="true" />
          </div>
          {requestedCrop ? (
            <div className="top-crop-grid selected-crop-grid">
              <TopCrop crop={requestedCrop} assessmentSessionId={assessmentSessionId} showRank={false} />
            </div>
          ) : (
            <div className="form-error" role="alert">The selected crop result is unavailable. Start a new assessment and try again.</div>
          )}
        </section>
      ) : (
        <>
      <section className="top-results-section" aria-labelledby="top-results-heading">
        <div className="section-title-row results-section-title">
          <div><h2 id="top-results-heading">Top eligible crops</h2><p>Ranked by the deterministic engine for this prepared evidence run.</p></div>
          <CircleGauge size={20} aria-hidden="true" />
        </div>
        <div className="top-crop-grid">{groups.topThree.map((crop) => <TopCrop crop={crop} assessmentSessionId={assessmentSessionId} key={crop.crop_id} />)}</div>
      </section>

      <section className="all-rankings-section" aria-labelledby="eligible-rankings-heading">
        <div className="section-title-row results-section-title">
          <div><h2 id="eligible-rankings-heading">Complete eligible ranking</h2><p>Suitability and confidence are separate measures. Lower confidence does not become a lower suitability score.</p></div>
          <BarChart3 size={20} aria-hidden="true" />
        </div>
        <EligibleTable crops={groups.eligible} assessmentSessionId={assessmentSessionId} />
      </section>

      <section className="ineligible-section" aria-labelledby="ineligible-heading">
        <div className="section-title-row results-section-title">
          <div><h2 id="ineligible-heading">Not supported in this region</h2><p>These crops retain their overall engine rank but are excluded from the eligible ranking.</p></div>
          <AlertTriangle size={20} aria-hidden="true" />
        </div>
        {groups.ineligible.map((crop) => {
          const regionalGate = crop.applied_gates.find((gate) => gate.gate === "unsupported_region");
          return (
            <article className="ineligible-crop" key={crop.crop_id}>
              <span className="ineligible-icon"><Sprout size={19} aria-hidden="true" /></span>
              <div><h3><Link className="ranking-crop-link" href={`/assessments/${assessmentSessionId}/crops/${crop.crop_id}`}>{crop.crop_name}<ChevronRight size={13} aria-hidden="true" /></Link></h3><p>{regionalGate?.reason ?? "The crop catalog does not support this crop in the selected region."}</p></div>
              <dl><div><dt>Overall rank</dt><dd>{crop.overall_rank}</dd></div><div><dt>Suitability</dt><dd>{formatScore(crop.suitability_score)}/100</dd></div><div><dt>Confidence</dt><dd>{formatScore(crop.confidence_score)}/100</dd></div></dl>
            </article>
          );
        })}
      </section>
        </>
      )}

      <section className="result-limitations" aria-labelledby="limitations-heading">
        <Info size={18} aria-hidden="true" />
        <div><h2 id="limitations-heading">How to read this result</h2><p>This is preliminary crop suitability, not a yield guarantee or irrigation prescription. The catalog and scoring coefficients remain provisional pending external agronomic review.</p>
          <details><summary>Assessment limitations <span>{recommendation.limitations.length}</span></summary><ul>{recommendation.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}</ul></details>
        </div>
      </section>

      <footer className="results-footer">
        <span><CheckCircle2 size={16} aria-hidden="true" />{isRequestedCropAssessment ? `${requestedCropName} assessment complete.` : "All 22 catalog crops are represented."}</span>
        <div><Link className="button button-primary" href={`/assessments/${assessmentSessionId}/scenarios`}>Compare scenarios<ChevronRight size={17} aria-hidden="true" /></Link><Link className="button button-secondary" href="/farm"><ArrowLeft size={17} aria-hidden="true" />New farm assessment</Link></div>
      </footer>
    </main>
  );
}
