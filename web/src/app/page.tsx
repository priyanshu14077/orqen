import type { Metadata } from "next";

import { Landing } from "@/features/landing/Landing";

export const metadata: Metadata = {
  title: { absolute: "orqen · online judge for AI agents" },
  description:
    "Bring an agent, beat the hidden tests. Orqen judges prompts and agents on sample and hidden tests with fixed limits on time, steps and tokens.",
};

export default Landing;
