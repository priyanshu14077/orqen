import { redirect } from "next/navigation";

export default async function ProblemPage({ params }: { params: Promise<{ problemId: string }> }) {
  redirect(`/p/${(await params).problemId}/submit`);
}
