/** Static export: the demo is plain files, so it works with no backend running (FR-015). */
// NEXT_BASE_PATH serves the export under a sub-path, e.g. "/ai-agentops" for GitHub Pages;
// unset (local builds, CI e2e) it stays at the site root.
const basePath = process.env.NEXT_BASE_PATH ?? "";

const nextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};

export default nextConfig;
