import { TopBar } from "@/components";
import type { Tab } from "@/components/TopBar/TopBar";
import { getMe } from "@/lib/server/viewer";

import styles from "./layout.module.css";

/**
 * The persistent frame: top bar with brand, numbered tabs and the signed-in handle.
 * The admin tab appears only for admins, but the admin route checks the role itself.
 */
export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const me = await getMe();
  const tabs: Tab[] = [
    { key: "problems", label: "problems", href: "/problems", match: "^/(problems|p/)" },
    { key: "judge", label: "judge", href: "/submissions", match: "^/(s/|submissions)" },
    { key: "contest", label: "contest", href: "/c/round-1/standings", match: "^/c/" },
  ];
  if (me.role === "admin") {
    tabs.push({ key: "admin", label: "admin", href: "/admin/rules/invoice-extractor", match: "^/admin" });
  }
  return (
    <div className={styles.shell}>
      <a href="#main" className="sr-only">
        skip to content
      </a>
      <TopBar tabs={tabs} handle={me.handle} plan={me.plan_id} />
      <main id="main" className={styles.main}>
        {children}
      </main>
    </div>
  );
}
