/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    // Agent servisinin adresi; docker-compose'da servis adıyla override edilir
    NEXT_PUBLIC_AGENT_URL: process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
