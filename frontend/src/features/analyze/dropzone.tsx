"use client";

import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { ALLOWED_EXTENSIONS, FILE_ICONS, PARSE_HINTS } from "@/constants/upload";
import { cn } from "@/lib/utils";

interface DropzoneProps {
  file: File | null;
  onFileSelect: (file: File) => void;
  error?: string | null;
}

function extOf(file: File): string {
  return file.name.split(".").pop()?.toLowerCase() ?? "";
}

export function Dropzone({ file, onFileSelect, error }: DropzoneProps) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const ext = file ? extOf(file) : null;

  return (
    <div>
      <div
        onClick={() => inputRef.current?.click()}
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          const dropped = e.dataTransfer.files[0];
          if (dropped) onFileSelect(dropped);
        }}
        className={cn(
          "upload-zone-border relative min-h-[200px] cursor-pointer rounded-2xl p-[1.5px] transition-transform",
          dragging && "scale-[1.01]",
        )}
      >
        <div
          className={cn(
            "flex min-h-[196px] flex-col items-center justify-center rounded-2xl bg-[var(--surface)] p-8 text-center transition-colors",
            file && "bg-[rgba(0,255,136,0.04)]",
          )}
        >
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept={ALLOWED_EXTENSIONS.map((e) => `.${e}`).join(",")}
            onChange={(e) => {
              const selected = e.target.files?.[0];
              if (selected) onFileSelect(selected);
            }}
          />

          {file ? (
            <>
              <div className="mb-3 flex size-14 items-center justify-center rounded-full border border-[rgba(0,255,136,0.3)] bg-[rgba(0,255,136,0.08)] text-2xl">
                {FILE_ICONS[ext ?? ""] ?? "✅"}
              </div>
              <div className="font-mono text-base font-medium text-[var(--green)]">
                {file.name}
              </div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">
                {(file.size / 1024).toFixed(1)} KB · click to change
              </div>
              {ext && PARSE_HINTS[ext] && (
                <div className="mt-2 font-mono text-[11px] text-muted-foreground">
                  {PARSE_HINTS[ext]}
                </div>
              )}
            </>
          ) : (
            <>
              <UploadCloud className="mb-3 size-12 text-[var(--cyan)]" strokeWidth={1.5} />
              <div className="text-lg text-foreground">Drop your infrastructure file</div>
              <div className="mt-1 font-mono text-xs text-muted-foreground">
                .tfstate · .json · .csv · .xlsx · .tf
              </div>
            </>
          )}
        </div>
      </div>
      {error && (
        <p className="mt-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
