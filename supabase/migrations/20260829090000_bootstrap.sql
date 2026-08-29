-- CropSage database bootstrap: shared extensions and stable contract enums.

create schema if not exists extensions;

create extension if not exists pgcrypto with schema extensions;
create extension if not exists postgis with schema extensions;
create extension if not exists pgtap with schema extensions;

create type public.assessment_session_status as enum (
  'active',
  'completed',
  'abandoned',
  'expired'
);

create type public.farm_profile_status as enum (
  'draft',
  'ready',
  'superseded'
);

create type public.provider_fetch_status as enum (
  'pending',
  'running',
  'succeeded',
  'failed'
);

create type public.provider_fetch_mode as enum (
  'live',
  'cache',
  'fallback'
);

create type public.evidence_source_type as enum (
  'provider',
  'farmer',
  'laboratory',
  'derived'
);

create type public.evidence_bundle_status as enum (
  'assembling',
  'partial',
  'validated',
  'failed'
);

create type public.recommendation_run_status as enum (
  'pending',
  'running',
  'scored',
  'validated',
  'completed',
  'failed'
);

create type public.evaluation_mode as enum (
  'planning',
  'planting_readiness'
);

create type public.crop_result_status as enum (
  'scored',
  'insufficient_evidence'
);

create type public.recommendation_class as enum (
  'recommended',
  'conditional',
  'not_recommended',
  'insufficient_evidence'
);

create type public.confidence_band as enum (
  'high',
  'medium',
  'low'
);

comment on type public.assessment_session_status is
  'Lifecycle for an assessment session.';
comment on type public.farm_profile_status is
  'Lifecycle for an immutable, versioned farm profile.';
comment on type public.provider_fetch_status is
  'Normalized lifecycle for one provider HTTP attempt.';
comment on type public.provider_fetch_mode is
  'Whether evidence came from a live request, reusable cache, or fallback artifact.';
comment on type public.evidence_source_type is
  'Origin class retained on every normalized evidence record.';
comment on type public.evidence_bundle_status is
  'Assembly and validation lifecycle for an EvidenceBundle.';
comment on type public.recommendation_run_status is
  'Deterministic recommendation lifecycle; failed is reachable from active states.';
comment on type public.evaluation_mode is
  'Engine evaluation modes defined by the recommendation contract.';
comment on type public.crop_result_status is
  'Per-crop scoring states defined by the recommendation contract.';
comment on type public.recommendation_class is
  'Farmer-facing recommendation classes produced by the deterministic engine.';
comment on type public.confidence_band is
  'Confidence bands defined by the recommendation contract.';
