import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { RuleEditor } from "@/features/admin/RuleEditor";
import { getMe } from "@/lib/server/viewer";

export const metadata: Metadata = { title: "eval rules" };

type Props = { params: Promise<{ ruleId: string }> };

/** Admins only. Hiding the tab is not the control; this check is (and the API's, later). */
export default async function RulePage({ params }: Props) {
  const me = await getMe();
  if (me.role !== "admin") notFound();
  const { ruleId } = await params;
  if (!/^[a-z0-9][a-z0-9-]{1,62}$/.test(ruleId)) notFound();
  return <RuleEditor ruleName={ruleId} />;
}
