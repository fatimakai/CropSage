import { z } from "zod";

export const progressEventSchema = z.object({
  sequenceNumber: z.number().int().positive(),
  kind: z.enum(["provider", "evidence", "scoring", "validation", "system"]),
  name: z.string().regex(/^[a-z][a-z0-9_.-]{1,99}$/),
  status: z.enum(["started", "succeeded", "failed", "info"]),
  safeSummary: z.string().min(1).max(500),
  cacheState: z.enum(["live", "cache", "fallback"]).nullable().optional(),
  occurredAt: z.iso.datetime(),
});

export const validationStateSchema = z.object({
  outcome: z.enum(["passed", "rejected"]),
  renderAllowed: z.boolean(),
  errors: z.array(z.string()),
  warnings: z.array(z.string()),
});

export const analysisProgressModeSchema = z.enum(["success", "fallback", "failure"]);

export const analysisProgressSnapshotSchema = z.object({
  assessmentSessionId: z.uuid(),
  status: z.enum(["running", "completed", "failed"]),
  outcome: z.enum(["success", "fallback", "failure"]).nullable(),
  terminal: z.boolean(),
  events: z.array(progressEventSchema),
});

export type ProgressEvent = z.infer<typeof progressEventSchema>;
export type ValidationState = z.infer<typeof validationStateSchema>;
export type AnalysisProgressMode = z.infer<typeof analysisProgressModeSchema>;
export type AnalysisProgressSnapshot = z.infer<typeof analysisProgressSnapshotSchema>;
