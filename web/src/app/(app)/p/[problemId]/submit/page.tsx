import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { SubmitView } from "@/features/submit/SubmitView";
import type { Problem, Standing } from "@/lib/api/types";
import { gateway, GatewayError } from "@/lib/server/gateway";
import { isUuid } from "@/lib/uuid";

export const metadata: Metadata = { title: "submit" };

type Props = { params: Promise<{ problemId: string }> };

export default async function SubmitPage({ params }: Props) {
  const { problemId } = await params;
  if (!isUuid(problemId)) notFound();
  const [problem, board] = await Promise.all([
    gateway<Problem>(`/v1/problems/${problemId}`),
    gateway<Standing[]>(`/v1/problems/${problemId}/leaderboard?limit=10`),
  ]).catch((err: unknown) => {
    if (err instanceof GatewayError && err.status === 404) notFound();
    throw err;
  });
  return <SubmitView problem={problem} leaderboard={board} />;
}
