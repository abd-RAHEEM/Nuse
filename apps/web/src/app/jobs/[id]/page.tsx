import JobDetailClient from "@/components/job-detail-client";

export const instant = false;

export default async function JobDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <JobDetailClient id={id} />;
}
