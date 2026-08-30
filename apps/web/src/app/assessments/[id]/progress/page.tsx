import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { AnalysisProgress } from "@/components/progress/analysis-progress";
import { userOwnsAssessment } from "@/lib/assessments/access";

export const dynamic = "force-dynamic";

type ProgressPageProps = {
  params: Promise<{ id: string }>;
};

export default async function ProgressPage({ params }: ProgressPageProps) {
  const { id } = await params;

  if (!(await userOwnsAssessment(id))) {
    notFound();
  }

  return (
    <AppShell>
      <AnalysisProgress assessmentSessionId={id} />
    </AppShell>
  );
}
