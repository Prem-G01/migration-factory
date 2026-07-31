import type { ReactNode } from "react";
import { TopNav } from "@/components/layout/top-nav";
import { AppBackground } from "@/components/canvas/app-background";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="relative flex h-screen flex-col overflow-hidden">
      <AppBackground />
      <div className="relative z-[1] flex h-full flex-col">
        <TopNav />
        <main className="flex-1 overflow-hidden">{children}</main>
      </div>
    </div>
  );
}
