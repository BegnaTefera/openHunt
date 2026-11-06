/** @type {import('next').NextConfig} */
const apiUrl = (process.env.API_URL ?? 'http://localhost:8000').replace(/\/+$/, '');

const nextConfig = {
  reactStrictMode: true,
  // The browser only ever talks to this site's /api. Next.js forwards those requests to
  // the real API, so the login cookie stays first-party and the API URL stays private.
  async rewrites() {
    return [{ source: '/api/:path*', destination: `${apiUrl}/:path*` }];
  },
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ];
  },
};

export default nextConfig;
