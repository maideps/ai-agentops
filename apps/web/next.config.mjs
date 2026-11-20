/** Static export: the demo is plain files, so it works with no backend running (FR-015). */
const nextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  poweredByHeader: false,
};

export default nextConfig;
