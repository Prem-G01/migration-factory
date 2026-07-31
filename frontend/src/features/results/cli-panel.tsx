"use client";

import { useState } from "react";
import { toast } from "sonner";
import { Copy, Check, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { API_BASE_URL, API_KEY } from "@/lib/config";

interface CliPanelProps {
  runId: string;
  targetProvider: string;
  direction: string;
}

function buildScript(runId: string, targetProvider: string): string {
  const credentialHint =
    targetProvider === "gcp"
      ? "gcloud auth application-default login   # GCP target — needs your own gcloud credentials"
      : "aws configure                           # AWS target — needs your own AWS credentials";

  return `#!/usr/bin/env bash
set -euo pipefail

# Migration Factory CLI — run ${runId.slice(0, 8)}
#
# Downloads the generated Terraform and applies it against YOUR cloud
# account using YOUR local credentials. Migration Factory never sees
# or stores your credentials — everything below runs on your machine.
#
# Prerequisites:
#   terraform >= 1.5
#   ${credentialHint}

RUN_ID="${runId}"

curl -sSL -H "X-API-Key: ${API_KEY || "<your-api-key>"}" \\
  "${API_BASE_URL}/api/v1/terraform/$RUN_ID" -o terraform.zip

unzip -o terraform.zip -d "migration-$RUN_ID"
cd "migration-$RUN_ID"

terraform init
terraform plan

# terraform apply will print the full plan again and require you to
# type "yes" before changing anything — nothing here is automatic.
terraform apply
`;
}

export function CliPanel({ runId, targetProvider, direction }: CliPanelProps) {
  const [copied, setCopied] = useState(false);
  const script = buildScript(runId, targetProvider);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(script);
      setCopied(true);
      toast.success("Copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Couldn't copy — select the text manually");
    }
  };

  return (
    <Dialog>
      <DialogTrigger
        render={
          <Button variant="outline" className="flex-1 gap-1.5">
            <Terminal className="size-4" />
            CLI
          </Button>
        }
      />
      <DialogContent className="max-w-2xl">
        <DialogTitle>Run with your own CLI</DialogTitle>
        <DialogDescription>
          {direction} · This runs entirely on your machine, using your own AWS/GCP credentials. Migration
          Factory never receives or stores them.
        </DialogDescription>

        <div className="relative mt-4">
          <pre className="max-h-96 overflow-auto rounded-xl border border-[var(--glass-border)] bg-[var(--glass-1)] p-4 font-mono text-[12.5px] leading-relaxed text-foreground/90">
            {script}
          </pre>
          <Button
            size="sm"
            variant="outline"
            onClick={handleCopy}
            className="absolute top-3 right-3 gap-1.5 bg-[var(--popover)]"
          >
            {copied ? <Check className="size-3.5 text-[var(--green)]" /> : <Copy className="size-3.5" />}
            {copied ? "Copied" : "Copy"}
          </Button>
        </div>

        <p className="mt-3 rounded-lg border border-[var(--glass-border-soft)] bg-[var(--glass-1)] px-3 py-2 text-[11px] text-muted-foreground">
          ⓘ <code className="font-mono">terraform apply</code> shows the full plan and asks for a typed
          &quot;yes&quot; before it changes anything in your account — review it carefully first.
        </p>
      </DialogContent>
    </Dialog>
  );
}
