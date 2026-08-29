"use client";

import { createBrowserClient } from "@supabase/ssr";

import { getPublicSupabaseEnvironment } from "@/lib/env";

export function createBrowserSupabaseClient() {
  const environment = getPublicSupabaseEnvironment();

  if (!environment) {
    throw new Error("Supabase public environment variables are not configured.");
  }

  return createBrowserClient(environment.url, environment.publishableKey);
}
