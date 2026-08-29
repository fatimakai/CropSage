export type PublicSupabaseEnvironment = {
  url: string;
  publishableKey: string;
};

export function getPublicSupabaseEnvironment(): PublicSupabaseEnvironment | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const publishableKey =
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ??
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !publishableKey) {
    return null;
  }

  return { url, publishableKey };
}

export function getScoringApiUrl(): string | null {
  return process.env.SCORING_API_URL ?? null;
}

export function getServerSupabaseEnvironment() {
  const publicEnvironment = getPublicSupabaseEnvironment();
  const secretKey =
    process.env.SUPABASE_SECRET_KEY ?? process.env.SUPABASE_SERVICE_ROLE_KEY;

  if (!publicEnvironment || !secretKey) {
    return null;
  }

  return { ...publicEnvironment, secretKey };
}
