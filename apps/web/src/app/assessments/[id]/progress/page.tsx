import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { AnalysisProgress } from "@/components/progress/analysis-progress";
import { userOwnsAssessment } from "@/lib/assessments/access";
import { parseProgressMode } from "@/lib/assessments/mock-progress";

export const dynamic = "force-dynamic";

type ProgressPageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ mode?: string | string[] }>;
};

export default async function ProgressPage({ params, searchParams }: ProgressPageProps) {
  const { id } = await params;
  const query = await searchParams;
  const mode = parseProgressMode(typeof query.mode === "string" ? query.mode : null);

  if (!(await userOwnsAssessment(id))) {
    notFound();
  }

  return (
    <AppShell>
      <AnalysisProgress assessmentSessionId={id} mode={mode} />
    </AppShell>
  );
}
