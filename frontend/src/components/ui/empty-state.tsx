import type { ReactNode } from "react";

export function EmptyState({
  icon,
  message,
  action,
}: {
  icon: ReactNode;
  message: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-10 text-center">
      <div className="text-2xl">{icon}</div>
      <p className="max-w-xs text-sm text-muted-foreground">{message}</p>
      {action}
    </div>
  );
}
