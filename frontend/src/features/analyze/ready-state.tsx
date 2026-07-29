const CAPABILITY_TAGS = [
  "AWS → GCP",
  "GCP → AWS",
  "Security Analysis",
  "Compliance Check",
  "FinOps Savings",
];

export function ReadyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5 p-8 text-center">
      <div className="animate-fade-up text-8xl opacity-10">🌌</div>
      <h2 className="animate-fade-up text-2xl font-semibold text-muted-foreground" style={{ animationDelay: "50ms" }}>
        Ready to analyze
      </h2>
      <div className="flex flex-wrap justify-center gap-2">
        {CAPABILITY_TAGS.map((tag, i) => (
          <span
            key={tag}
            className="animate-fade-up rounded-full border border-white/10 bg-white/[0.03] px-3.5 py-1.5 font-mono text-xs text-muted-foreground opacity-0"
            style={{ animationDelay: `${100 + i * 50}ms` }}
          >
            {tag}
          </span>
        ))}
      </div>
    </div>
  );
}
