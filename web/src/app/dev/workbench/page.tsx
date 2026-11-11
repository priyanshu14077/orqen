import { notFound } from "next/navigation";

import { Workbench } from "./Workbench";

/**
 * The component workbench: every primitive with a fixture for each verdict and stage
 * (docs/frontend §9). Development only; production builds return 404.
 */
export default function WorkbenchPage() {
  if (process.env.NODE_ENV === "production") notFound();
  return <Workbench />;
}
