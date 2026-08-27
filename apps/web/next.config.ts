import type { NextConfig } from "next";

const apiBase = process.env.API_INTERNAL_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [{ source: "/backend/:path*", destination: `${apiBase}/:path*` }];
  },
};

export default nextConfig;
