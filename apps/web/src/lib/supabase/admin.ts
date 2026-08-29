import "server-only";

import { createClient } from "@supabase/supabase-js";

import { getServerSupabaseEnvironment } from "@/lib/env";

export function createAdminSupabaseClient() {
  const environment = getServerSupabaseEnvironment();

  if (!environment) {
    throw new Error("Supabase server environment variables are not configured.");
  }

  return createClient(environment.url, environment.secretKey, {
    auth: {
      autoRefreshToken: false,
      detectSessionInUrl: false,
      persistSession: false,
    },
  });
}
