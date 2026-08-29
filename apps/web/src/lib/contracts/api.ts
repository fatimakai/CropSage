import { z } from "zod";

export const apiErrorSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
});

export const sessionBootstrapResponseSchema = z.discriminatedUnion("ok", [
  z.object({
    ok: z.literal(true),
    userId: z.uuid(),
    isAnonymous: z.boolean(),
  }),
  z.object({
    ok: z.literal(false),
    error: apiErrorSchema,
  }),
]);

export const createFarmProfileResponseSchema = z.discriminatedUnion("ok", [
  z.object({
    ok: z.literal(true),
    assessmentSessionId: z.uuid(),
    farmProfileId: z.uuid(),
    externalProfileId: z.string().min(1),
  }),
  z.object({
    ok: z.literal(false),
    error: apiErrorSchema,
  }),
]);

export type ApiError = z.infer<typeof apiErrorSchema>;
export type SessionBootstrapResponse = z.infer<typeof sessionBootstrapResponseSchema>;
export type CreateFarmProfileResponse = z.infer<typeof createFarmProfileResponseSchema>;
