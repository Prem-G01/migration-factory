"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  LayoutDashboard,
  History,
  UploadCloud,
  ExternalLink,
} from "lucide-react";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useUIStore } from "@/hooks/use-ui-store";
import { useRuns } from "@/hooks/use-migration-queries";
import { directionColor } from "@/constants/theme";

export function CommandPalette() {
  const { commandPaletteOpen, setCommandPaletteOpen } = useUIStore();
  const router = useRouter();
  // Only fetch run history once the palette is actually open — no point
  // holding a background poll running for a UI element most sessions
  // never open.
  const { data } = useRuns();

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setCommandPaletteOpen(!commandPaletteOpen);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [commandPaletteOpen, setCommandPaletteOpen]);

  const go = (path: string) => {
    setCommandPaletteOpen(false);
    router.push(path);
  };

  return (
    <CommandDialog
      open={commandPaletteOpen}
      onOpenChange={setCommandPaletteOpen}
      title="Command Palette"
      description="Jump to a page or a recent run"
    >
      <CommandInput placeholder="Type a command or search runs..." />
      <CommandList>
        <CommandEmpty>No results found.</CommandEmpty>
        <CommandGroup heading="Navigate">
          <CommandItem onSelect={() => go("/")}>
            <UploadCloud />
            Analyze new infrastructure
          </CommandItem>
          <CommandItem onSelect={() => go("/dashboard")}>
            <LayoutDashboard />
            Dashboard
          </CommandItem>
          <CommandItem onSelect={() => go("/history")}>
            <History />
            History
          </CommandItem>
        </CommandGroup>
        {data && data.runs.length > 0 && (
          <CommandGroup heading="Recent runs">
            {data.runs.slice(0, 8).map((run) => (
              <CommandItem
                key={run.run_id}
                onSelect={() => go(`/results?run=${run.run_id}`)}
              >
                <ExternalLink style={{ color: directionColor(run.direction) }} />
                <span>{run.direction}</span>
                <span className="ml-auto font-mono text-xs text-muted-foreground">
                  {run.resources} resources
                </span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  );
}
