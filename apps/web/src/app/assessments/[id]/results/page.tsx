import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { RecommendationResults } from "@/components/recommendations/recommendation-results";
import { userOwnsAssessment } from "@/lib/assessments/access";
import { getPreparedRecommendationResult } from "@/lib/recommendations/prepared-results";

export const dynamic = "force-dynamic";

type ResultsPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ validation?: string | string[] }>;
};

export default async function ResultsPage({ params, searchParams }: ResultsPageProps) {
  const { id } = await params;
  const query = await searchParams;

  if (!(await userOwnsAssessment(id))) {
    notFound();
  }

  const previewBlocked =
    process.env.NODE_ENV !== "production" && query.validation === "blocked";
  const result = getPreparedRecommendationResult({ previewBlocked });

  return (
    <AppShell>
      <RecommendationResults assessmentSessionId={id} result={result} />
    </AppShell>
  );
}
