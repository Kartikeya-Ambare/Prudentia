import type { ReactNode } from "react";

/** One page's content, with a short fade-and-settle when it opens. */
export function RoutePanel({ active, children }: { active: boolean; children: ReactNode }) {
  return (
    <div hidden={!active} className="route-panel pt-6">
      {children}
    </div>
  );
}
