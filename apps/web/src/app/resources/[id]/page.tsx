import ResourceDetailClient from "@/components/resource-detail-client";

export const instant = false;

export default async function ResourceDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ResourceDetailClient id={id} />;
}
