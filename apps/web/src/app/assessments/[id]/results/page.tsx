import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { RecommendationResults } from "@/components/recommendations/recommendation-results";
import { userOwnsAssessment } from "@/lib/assessments/access";
import { getPersistedRecommendationResult } from "@/lib/recommendations/persisted-results";

export const dynamic = "force-dynamic";

type ResultsPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ResultsPage({ params }: ResultsPageProps) {
  const { id } = await params;

  if (!(await userOwnsAssessment(id))) {
    notFound();
  }

  const result = await getPersistedRecommendationResult(id);

  return (
    <AppShell>
      <RecommendationResults assessmentSessionId={id} result={result} />
    </AppShell>
  );
}
