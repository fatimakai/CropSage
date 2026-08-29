import { notFound } from "next/navigation";

import { AppShell } from "@/components/app-shell";
import { CropDetail } from "@/components/crops/crop-detail";
import { userOwnsAssessment } from "@/lib/assessments/access";
import { getPreparedCropDetail } from "@/lib/crops/prepared-crop-details";

export const dynamic = "force-dynamic";

type CropDetailPageProps = {
  params: Promise<{ id: string; cropId: string }>;
};

export default async function CropDetailPage({ params }: CropDetailPageProps) {
  const { id, cropId } = await params;

  if (!(await userOwnsAssessment(id))) notFound();

  const detail = getPreparedCropDetail(cropId);
  if (detail.state !== "ready") notFound();

  return <AppShell><CropDetail assessmentSessionId={id} detail={detail} /></AppShell>;
}
