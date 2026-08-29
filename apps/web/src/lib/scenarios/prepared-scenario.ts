import "server-only";

import engineInputFixture from "../../../../../handoff/fatima_scoring_migrations/sample_engine_input.json";

import { farmProfileSnapshotSchema } from "@/lib/contracts";
import { getPreparedRecommendationResult } from "@/lib/recommendations/prepared-results";

export function getPreparedScenarioWorkspace() {
  const baseline = getPreparedRecommendationResult();
  if (baseline.state === "blocked") return baseline;

  return {
    state: "ready" as const,
    baseline: baseline.recommendation,
    validation: baseline.validation,
    profile: farmProfileSnapshotSchema.parse(engineInputFixture),
    scenarioStatus: "awaiting_production_integration" as const,
  };
}
