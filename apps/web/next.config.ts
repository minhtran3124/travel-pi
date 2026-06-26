import path from "node:path";
import type { NextConfig } from "next";

// Proxy FE → FastAPI backend. In dev the BE runs on :8000 (`make api`).
// Override with NEXT_PUBLIC_API_URL for other environments.
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // Pin the workspace root to the monorepo root (avoids picking a stray
  // lockfile elsewhere on the machine).
  turbopack: {
    root: path.join(__dirname, "..", ".."),
  },
  async rewrites() {
    return [
      {
        source: "/api/be/:path*",
        destination: `${API_URL}/:path*`,
      },
    ];
  },
};

export default nextConfig;
