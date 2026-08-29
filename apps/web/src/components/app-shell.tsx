import { Sprout } from "lucide-react";
import type { ReactNode } from "react";

import { SessionBootstrap } from "@/components/session-bootstrap";

type AppShellProps = {
  children: ReactNode;
};

export function AppShell({ children }: AppShellProps) {
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-lockup" aria-label="CropSage">
          <span className="brand-mark" aria-hidden="true">
            <Sprout size={21} strokeWidth={2.2} />
          </span>
          <span>CropSage</span>
        </div>
        <SessionBootstrap />
      </header>
      {children}
    </div>
  );
}
