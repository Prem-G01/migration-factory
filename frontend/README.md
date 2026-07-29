# Migration Factory AI — Frontend

Next.js 15 + React 19 + TypeScript frontend for Migration Factory, an
AI-powered AWS ↔ GCP infrastructure migration platform. Talks to the
FastAPI backend in `../src/migration_factory/api/`.

## Stack

- Next.js 15 (App Router), TypeScript (strict), Tailwind CSS v4
- shadcn/ui (`base-nova` style, Base UI primitives)
- `motion` (Framer Motion) for animation
- TanStack React Query for data fetching, Zustand for lightweight UI state
- Recharts for charts

This app has no server-only features (no API routes, no server actions) —
every page fetches client-side against the external FastAPI backend, so
production builds are always a static export (`output: "export"` in
`next.config.ts`), served by nginx (Docker) or GitHub Pages.

## Development

```bash
npm install
npm run dev
```

Open <http://localhost:3000>. Set `NEXT_PUBLIC_API_URL` (defaults to
`http://localhost:8000`) if the backend runs somewhere else — see
`.env.local` for local overrides (gitignored).

## Build

```bash
npm run build
```

Outputs a static export to `out/`. Set `GITHUB_PAGES=true` to build with
the `/migration-factory` base path used by
`.github/workflows/deploy-frontend.yml`; leave it unset for the Docker
build, which serves at the root.

## Project structure

```text
src/
  app/          Next.js routes (/, /results, /history, /dashboard)
  features/     Page-level feature components (upload, results, history, dashboard)
  components/
    ui/         Design-system primitives (Button, Card, GlassCard, MetricCard, ...)
    layout/     App shell (Sidebar, Header, CommandPalette)
    data/       Data display (DataTable, Charts, Timeline, ScoreRing)
  services/     API client — one function per real backend endpoint
  hooks/        React Query hooks + Zustand store
  types/        TypeScript types mirroring the real API response shapes
  constants/    Design tokens, upload-form option lists
```

## Routes

`/results` uses a `?run=<id>` query param rather than a `/results/[runId]`
path segment — a dynamic path segment can't be statically exported since
Next.js needs build-time-known params for every route, but run IDs are
created at runtime by the backend. The query-param page is a single
static file whose content resolves entirely client-side.
