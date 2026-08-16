/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  env: {
    // Address of the agent service; override with the service name under docker-compose
    NEXT_PUBLIC_AGENT_URL: process.env.NEXT_PUBLIC_AGENT_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
