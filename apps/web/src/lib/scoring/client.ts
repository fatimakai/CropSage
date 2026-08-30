import "server-only";

import {
  recommendationExecutionSchema,
  recommendationOutputSchema,
  type RecommendationExecution,
  type RecommendationOutput,
  type ScoringRequest,
} from "@/lib/contracts";
import { getScoringApiUrl } from "@/lib/env";

export interface ScoringGateway {
  score(request: ScoringRequest): Promise<RecommendationOutput>;
}

export class FastApiScoringGateway implements ScoringGateway {
  constructor(private readonly baseUrl = getScoringApiUrl()) {}

  async score(request: ScoringRequest): Promise<RecommendationOutput> {
    if (!this.baseUrl) {
      throw new Error("SCORING_API_URL is not configured.");
    }

    const response = await fetch(new URL("/v1/recommendations/score", this.baseUrl), {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(request),
      cache: "no-store",
    });

    if (!response.ok) {
      throw new Error(`Scoring service returned HTTP ${response.status}.`);
    }

    return recommendationOutputSchema.parse(await response.json());
  }

  async execute(farmProfile: Record<string, unknown>): Promise<RecommendationExecution> {
    if (!this.baseUrl) {
      throw new Error("SCORING_API_URL is not configured.");
    }

    const response = await fetch(new URL("/v1/recommendations/execute", this.baseUrl), {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ farm_profile: farmProfile }),
      cache: "no-store",
      signal: AbortSignal.timeout(45_000),
    });

    if (!response.ok) {
      throw new Error(`Recommendation service returned HTTP ${response.status}.`);
    }

    return recommendationExecutionSchema.parse(await response.json());
  }
}
