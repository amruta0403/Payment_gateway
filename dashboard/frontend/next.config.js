/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [
      {
        source: '/bff/:path*',
        destination: `${process.env.NEXT_PUBLIC_BFF_URL || 'http://localhost:8099'}/:path*`,
      },
    ]
  },
}

module.exports = nextConfig
