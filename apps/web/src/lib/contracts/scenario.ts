import { z } from "zod";

export const scenarioTypeSchema = z.enum([
  "planting_timing",
  "irrigation_access",
  "combined",
]);

export const scenarioDraftSchema = z
  .object({
    scenario_type: scenarioTypeSchema,
    changes: z.object({
      planned_month: z.string().regex(/^\d{4}-(0[1-9]|1[0-2])$/).optional(),
      planting_flexibility_days: z.number().int().min(0).max(120).optional(),
      irrigation_availability: z.enum(["yes", "no", "unknown"]).optional(),
      irrigation_reliability: z
        .enum(["reliable", "limited", "seasonal", "unreliable", "unknown", "not_applicable"])
        .optional(),
    }),
    assumptions: z.array(z.string().min(1)).min(3),
  })
  .superRefine((draft, context) => {
    const keys = Object.keys(draft.changes);
    if (keys.length === 0) {
      context.addIssue({
        code: "custom",
        path: ["changes"],
        message: "A scenario must change at least one supported input.",
      });
    }
    if (
      draft.scenario_type === "planting_timing" &&
      !draft.changes.planned_month &&
      draft.changes.planting_flexibility_days === undefined
    ) {
      context.addIssue({
        code: "custom",
        path: ["changes"],
        message: "A planting scenario requires a planting-time change.",
      });
    }
    if (
      draft.scenario_type === "irrigation_access" &&
      !draft.changes.irrigation_availability &&
      !draft.changes.irrigation_reliability
    ) {
      context.addIssue({
        code: "custom",
        path: ["changes"],
        message: "An irrigation scenario requires an irrigation change.",
      });
    }
  });

export type ScenarioDraft = z.infer<typeof scenarioDraftSchema>;
export type ScenarioType = z.infer<typeof scenarioTypeSchema>;
