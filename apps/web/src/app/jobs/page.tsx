import { JobsView } from "@/components/jobs-view";
import { NuseShell } from "@/components/nuse-shell";

export default function JobsPage() {
  return <NuseShell title="Jobs" eyebrow="Keep the next move visible"><JobsView /></NuseShell>;
}
