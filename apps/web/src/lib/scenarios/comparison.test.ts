import { describe, expect, it } from "vitest";

import engineOutputFixture from "../../../../../handoff/fatima_scoring_migrations/sample_22_crop_engine_output.json";

import {
  recommendationOutputSchema,
  scenarioDraftSchema,
} from "@/lib/contracts";
import { compareValidatedScenarioOutputs } from "@/lib/scenarios/comparison";

const output = recommendationOutputSchema.parse(engineOutputFixture);

describe("scenario comparison", () => {
  it("requires supported changes and all three assumptions", () => {
    expect(
      scenarioDraftSchema.safeParse({
        scenario_type: "planting_timing",
        changes: {},
        assumptions: [],
      }).success,
    ).toBe(false);

    expect(
      scenarioDraftSchema.safeParse({
        scenario_type: "planting_timing",
        changes: { planned_month: "2026-09" },
        assumptions: ["Location unchanged", "Evidence refresh required", "Preliminary only"],
      }).success,
    ).toBe(true);
  });

  it("calculates deltas only from validator-authorized engine outputs", () => {
    const result = compareValidatedScenarioOutputs(output, output, {
      outcome: "passed",
      render_allowed: true,
      validator_version: "test-validator",
      warnings: [],
      errors: [],
    });

    expect(result.state).toBe("ready");
    if (result.state !== "ready") return;
    expect(result.rows).toHaveLength(22);
    expect(result.rows.every((row) => row.rankDelta === 0 && row.scoreDelta === 0)).toBe(true);
  });

  it("blocks all deltas when scenario validation is not allowed", () => {
    expect(
      compareValidatedScenarioOutputs(output, output, {
        outcome: "incomplete",
        render_allowed: false,
        validator_version: "test-validator",
        warnings: [],
        errors: ["Not validated"],
      }),
    ).toEqual({
      state: "blocked",
      reason: "The scenario validator has not authorized score or rank deltas for display.",
    });
  });
});
