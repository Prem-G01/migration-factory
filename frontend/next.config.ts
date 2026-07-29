import type { NextConfig } from "next";

// This app has no server-only features (no API routes, no server
// actions) — everything renders client-side against the external
// FastAPI backend — so production builds are always a static export,
// served by nginx (Docker) or GitHub Pages.
//
// GITHUB_PAGES is set only by .github/workflows/deploy-frontend.yml —
// local `next dev` and the Docker build both stay un-prefixed at the
// root; only the GitHub Pages build gets the /migration-factory prefix.
const isGithubPages = process.env.GITHUB_PAGES === "true";
const basePath = isGithubPages ? "/migration-factory" : "";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  images: { unoptimized: true },
  env: {
    NEXT_PUBLIC_BASE_PATH: basePath,
  },
};

export default nextConfig;
