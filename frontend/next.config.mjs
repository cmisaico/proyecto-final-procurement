/** @type {import('next').NextConfig} */
const BACKEND_URL = process.env.BACKEND_URL || "http://procurement.local";

const nextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source: "/api/v1/:path*",
        destination: `${BACKEND_URL}/api/v1/:path*`,
      },
    ];
  },
};

export default nextConfig;
