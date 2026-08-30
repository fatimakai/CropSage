import { defineRailway, github, preserve, project, service } from "railway/iac";

export default defineRailway(() => {
  const backendApi = service("backend-api", {
    source: github("fatimakai/CropSage"),
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile",
    },
    healthcheck: "/health",
    healthcheckTimeout: 300,
    replicas: { "ams": 1 },
    env: {
      CROP_CATALOG_VERSION: preserve(),
      ENABLE_API_DOCS: preserve(),
      EVIDENCE_BUNDLE_SCHEMA_VERSION: preserve(),
      FARM_PROFILE_SCHEMA_VERSION: preserve(),
      FORTYGUARD_API_KEY: preserve(),
      FORTYGUARD_BASE_URL: preserve(),
      GEMINI_API_KEY: preserve(),
      GEMINI_MODEL: preserve(),
      LOG_LEVEL: preserve(),
      MAX_REQUEST_BYTES: preserve(),
      OPENROUTER_MODEL: preserve(),
      OPEN_ROUTER_API_KEY: preserve(),
      RECOMMENDATION_SCHEMA_VERSION: preserve(),
      SCORING_ENGINE_VERSION: preserve(),
      SUPABASE_SERVICE_ROLE_KEY: preserve(),
      SUPABASE_URL: preserve(),
    },
  });
  const frontend = service("frontend", {
    build: {
      buildEnvironment: "V3",
      builder: "DOCKERFILE",
      dockerfilePath: "Dockerfile.frontend",
    },
    healthcheck: "/api/health",
    healthcheckTimeout: 300,
    replicas: { "ams": 1 },
    env: {
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: preserve(),
      NEXT_PUBLIC_SUPABASE_URL: preserve(),
      SCORING_API_URL: preserve(),
      SUPABASE_SECRET_KEY: preserve(),
    },
  });

  return project("discerning-presence", {
    resources: [backendApi, frontend],
  });
});
