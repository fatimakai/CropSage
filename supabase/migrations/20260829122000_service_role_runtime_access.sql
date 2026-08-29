-- Explicit backend access when automatic Data API table exposure is disabled.

grant usage on schema public to service_role;

grant select, insert, update on table
  public.assessment_sessions,
  public.farm_profiles,
  public.provider_fetches,
  public.evidence_records,
  public.evidence_bundles,
  public.evidence_bundle_records,
  public.recommendation_runs,
  public.crop_score_results,
  public.validation_reports,
  public.run_events
to service_role;

revoke delete, truncate on table
  public.assessment_sessions,
  public.farm_profiles,
  public.provider_fetches,
  public.evidence_records,
  public.evidence_bundles,
  public.evidence_bundle_records,
  public.recommendation_runs,
  public.crop_score_results,
  public.validation_reports,
  public.run_events
from service_role;

comment on schema public is
  'CropSage application schema. Browser access is restricted by grants and RLS; service_role owns server-side runtime writes.';
