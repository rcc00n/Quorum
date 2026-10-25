import type { NextConfig } from "next";
const config: NextConfig = {
  poweredByHeader: false,
  devIndicators: false,
  skipTrailingSlashRedirect: true,
  output: "standalone",
  async rewrites() {
    return process.env.NODE_ENV === "development"
      ? [
          {
            source: "/api/:path*",
            destination: "http://127.0.0.1:8017/api/:path*/",
          },
          {
            source: "/staff/:path*",
            destination: "http://127.0.0.1:8017/staff/:path*/",
          },
          {
            source: "/staff-static/:path*",
            destination: "http://127.0.0.1:8017/staff-static/:path*",
          },
        ]
      : [];
  },
};
export default config;
