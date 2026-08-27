/** @type {import('next').NextConfig} */
const apiTarget = (process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000").replace(/\/$/, "");

const nextConfig = {
  reactStrictMode: true,
  // Allow phones on the local Wi-Fi to receive Next.js development assets.
  allowedDevOrigins: ["10.21.4.107", "192.168.43.178", "localhost", "127.0.0.1"],
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${apiTarget}/api/:path*`,
      },
    ];
  },
};
module.exports = nextConfig;
