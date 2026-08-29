import type {
  RecommendationOutput,
  ValidationGate,
} from "@/lib/contracts";

export type ScenarioComparisonRow = {
  cropId: string;
  cropName: string;
  regionallyEligible: boolean;
  baselineScore: number | null;
  scenarioScore: number | null;
  scoreDelta: number | null;
  baselineRank: number;
  scenarioRank: number;
  rankDelta: number;
  baselineConfidence: number | null;
  scenarioConfidence: number | null;
  confidenceDelta: number | null;
};

export type ScenarioComparisonResult =
  | { state: "ready"; rows: ScenarioComparisonRow[] }
  | { state: "blocked"; reason: string };

function numericDelta(next: number | null, baseline: number | null) {
  if (next === null || baseline === null) return null;
  return Number((next - baseline).toFixed(2));
}

export function compareValidatedScenarioOutputs(
  baseline: RecommendationOutput,
  scenario: RecommendationOutput,
  scenarioValidation: ValidationGate,
): ScenarioComparisonResult {
  if (scenarioValidation.outcome !== "passed" || !scenarioValidation.render_allowed) {
    return {
      state: "blocked",
      reason: "The scenario validator has not authorized score or rank deltas for display.",
    };
  }

  const scenarioByCrop = new Map(scenario.rankings.map((crop) => [crop.crop_id, crop]));
  const rows: ScenarioComparisonRow[] = [];

  for (const baselineCrop of baseline.rankings) {
    const scenarioCrop = scenarioByCrop.get(baselineCrop.crop_id);
    if (!scenarioCrop) {
      return { state: "blocked", reason: "The scenario does not contain all baseline crops." };
    }

    rows.push({
      cropId: baselineCrop.crop_id,
      cropName: baselineCrop.crop_name,
      regionallyEligible: scenarioCrop.regionally_eligible,
      baselineScore: baselineCrop.suitability_score,
      scenarioScore: scenarioCrop.suitability_score,
      scoreDelta: numericDelta(scenarioCrop.suitability_score, baselineCrop.suitability_score),
      baselineRank: baselineCrop.overall_rank,
      scenarioRank: scenarioCrop.overall_rank,
      rankDelta: baselineCrop.overall_rank - scenarioCrop.overall_rank,
      baselineConfidence: baselineCrop.confidence_score,
      scenarioConfidence: scenarioCrop.confidence_score,
      confidenceDelta: numericDelta(scenarioCrop.confidence_score, baselineCrop.confidence_score),
    });
  }

  return { state: "ready", rows };
}
