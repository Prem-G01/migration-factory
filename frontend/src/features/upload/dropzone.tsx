"use client";

import { useRef, useState } from "react";
import { motion } from "motion/react";
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
      <motion.div
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
        animate={
          file
            ? { scale: [1, 1.01, 1] }
            : undefined
        }
        transition={{ duration: 0.3 }}
        className={cn(
          "relative cursor-pointer rounded-2xl border-1.5 border-dashed p-8 text-center transition-colors",
          file
            ? "border-[rgba(52,211,153,0.4)] bg-[rgba(52,211,153,0.04)]"
            : dragging
              ? "border-primary bg-primary/[0.06]"
              : "border-white/10 bg-white/[0.02] hover:border-white/20",
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

        <div className="relative mx-auto mb-3 flex size-14 items-center justify-center rounded-full border border-white/10">
          <span className="text-xl">{ext ? FILE_ICONS[ext] ?? "✅" : "📁"}</span>
          <div className="absolute inset-[-7px] rounded-full border border-dashed border-white/10" />
        </div>

        {file ? (
          <>
            <div className="font-mono text-sm font-medium text-[#34d399]">
              {file.name}
            </div>
            <div className="mt-1 font-mono text-xs text-muted-foreground">
              {(file.size / 1024).toFixed(1)} KB · click to change
            </div>
            <span className="mt-2 inline-block rounded-full border border-[rgba(52,211,153,0.25)] bg-[rgba(52,211,153,0.1)] px-2.5 py-0.5 font-mono text-[10px] text-[#34d399]">
              ● Ready to analyze
            </span>
            {ext && PARSE_HINTS[ext] && (
              <div className="mt-2 font-mono text-[10px] text-muted-foreground">
                {PARSE_HINTS[ext]}
              </div>
            )}
          </>
        ) : (
          <>
            <div className="mb-1 text-sm text-muted-foreground">
              Drop your infrastructure file here
            </div>
            <div className="font-mono text-[11px] text-muted-foreground/60">
              .tfstate · .json · .csv · .xlsx · .tf · .yaml
            </div>
          </>
        )}
      </motion.div>
      {error && (
        <p className="mt-2 rounded-lg border border-destructive/20 bg-destructive/5 px-3 py-2 text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
