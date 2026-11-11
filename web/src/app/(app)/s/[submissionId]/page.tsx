import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { JudgeView } from "@/features/judge/JudgeView";
import type { Snapshot } from "@/lib/api/types";
import { gateway, GatewayError } from "@/lib/server/gateway";
import { getMe } from "@/lib/server/viewer";
import { isUuid } from "@/lib/uuid";

export const metadata: Metadata = { title: "judging" };

type Props = { params: Promise<{ submissionId: string }> };

export default async function SubmissionPage({ params }: Props) {
  const { submissionId } = await params;
  if (!isUuid(submissionId)) notFound();
  const [snapshot, me] = await Promise.all([
    gateway<Snapshot>(`/v1/submissions/${submissionId}`),
    getMe(),
  ]).catch((err: unknown) => {
    if (err instanceof GatewayError && err.status === 404) notFound();
    throw err;
  });
  return <JudgeView key={submissionId} snapshot={snapshot} handle={me.handle} />;
}
