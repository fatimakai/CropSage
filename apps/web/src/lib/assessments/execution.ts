import "server-only";

import { createHash, randomUUID } from "node:crypto";

import type { RecommendationExecution } from "@/lib/contracts";
import { FastApiScoringGateway } from "@/lib/scoring/client";
import { createAdminSupabaseClient } from "@/lib/supabase/admin";

const providerEvidenceKeys = {
  nasa_power: "nasa_power_climate",
  open_meteo: "open_meteo_weather",
  ssurgo: "ssurgo_soil",
  fortyguard: "fortyguard_heat",
} as const;

function objectValue(value: unknown, label: string): Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} is missing from the prepared recommendation.`);
  }
  return value as Record<string, unknown>;
}

async function uploadProviderArtifacts(
  assessmentSessionId: string,
  execution: RecommendationExecution,
) {
  const supabase = createAdminSupabaseClient();
  const provenance = objectValue(execution.evidence_bundle.provenance, "Evidence provenance");
  const locationEvidence = objectValue(
    execution.evidence_bundle.location_evidence,
    "Location evidence",
  );
  const uploadId = randomUUID();
  const artifacts: Record<string, Record<string, unknown>> = {};

  for (const [provider, evidenceKey] of Object.entries(providerEvidenceKeys)) {
    const providerProvenance = objectValue(provenance[provider], `${provider} provenance`);
    const evidence = objectValue(locationEvidence[evidenceKey], `${provider} evidence`);
    const payload = JSON.stringify({ provider, provenance: providerProvenance, evidence });
    const sha256 = createHash("sha256").update(payload).digest("hex");
    const objectPath = `runs/${assessmentSessionId}/${uploadId}/${provider}.json`;
    const { error } = await supabase.storage
      .from("provider-artifacts")
      .upload(objectPath, payload, { contentType: "application/json", upsert: false });
    if (error) throw error;

    artifacts[provider] = {
      bucket_name: "provider-artifacts",
      object_path: objectPath,
      sha256,
      content_type: "application/json",
      size_bytes: Buffer.byteLength(payload),
      provider_timestamp:
        typeof providerProvenance.generated_at === "string"
          ? providerProvenance.generated_at
          : null,
      sanitization_version: "1.0.0",
      schema_version: String(execution.evidence_bundle.schema_version ?? "1.2.0"),
    };
  }

  return artifacts;
}

export async function executeAssessment(assessmentSessionId: string) {
  const supabase = createAdminSupabaseClient();
  const { data: existing, error: existingError } = await supabase
    .from("recommendation_runs")
    .select("id,status")
    .eq("assessment_session_id", assessmentSessionId)
    .eq("run_kind", "baseline")
    .eq("status", "completed")
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();
  if (existingError) throw existingError;
  if (existing) return { recommendationRunId: existing.id, created: false };

  const { data: session, error: sessionError } = await supabase
    .from("assessment_sessions")
    .select("active_profile_id")
    .eq("id", assessmentSessionId)
    .single();
  if (sessionError) throw sessionError;

  const { data: profile, error: profileError } = await supabase
    .from("farm_profiles")
    .select("profile_snapshot")
    .eq("id", session.active_profile_id)
    .single();
  if (profileError) throw profileError;

  const gateway = new FastApiScoringGateway();
  const execution = await gateway.execute(
    objectValue(profile.profile_snapshot, "Farm profile snapshot"),
  );
  const providerArtifacts = await uploadProviderArtifacts(assessmentSessionId, execution);
  const { data, error } = await supabase.rpc("persist_recommendation_execution", {
    p_assessment_session_id: assessmentSessionId,
    p_resolved_profile_snapshot: execution.farm_profile,
    p_location_resolution: execution.location_resolution,
    p_evidence_bundle_snapshot: execution.evidence_bundle,
    p_scoring_policy: execution.scoring_config,
    p_engine_output: execution.recommendation,
    p_validation_report: execution.validation_report,
    p_provider_artifacts: providerArtifacts,
  });
  if (error) throw error;

  const persisted = Array.isArray(data) ? data[0] : data;
  if (!persisted?.recommendation_run_id) {
    throw new Error("The recommendation run did not return a persisted identifier.");
  }
  return {
    recommendationRunId: String(persisted.recommendation_run_id),
    created: Boolean(persisted.created),
  };
}
