import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { ScenarioComparison } from "@/components/scenarios/scenario-comparison";
import { userOwnsAssessment } from "@/lib/assessments/access";
import { getPreparedScenarioWorkspace } from "@/lib/scenarios/prepared-scenario";

export const dynamic = "force-dynamic";

type ScenarioPageProps = { params: Promise<{ id: string }> };

export default async function ScenarioPage({ params }: ScenarioPageProps) {
  const { id } = await params;
  if (!(await userOwnsAssessment(id))) notFound();

  const workspace = getPreparedScenarioWorkspace();
  if (workspace.state !== "ready") notFound();

  return <AppShell><ScenarioComparison assessmentSessionId={id} baseline={workspace.baseline} profile={workspace.profile} /></AppShell>;
}
