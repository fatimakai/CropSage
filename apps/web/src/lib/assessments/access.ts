import "server-only";

import { createServerSupabaseClient } from "@/lib/supabase/server";

export async function userOwnsAssessment(assessmentSessionId: string) {
  const supabase = await createServerSupabaseClient();
  const { data: current } = await supabase.auth.getUser();

  if (!current.user) {
    return false;
  }

  const { data, error } = await supabase
    .from("assessment_sessions")
    .select("id")
    .eq("id", assessmentSessionId)
    .maybeSingle();

  return !error && Boolean(data);
}
