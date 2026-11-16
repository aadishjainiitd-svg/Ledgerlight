import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const lightError = path.join(here, 'lib', 'light-error.jsx');
const REPLACEMENTS = [
  [/\/next\/dist\/(esm\/)?pages\/_error(\.js)?$/, lightError],
  [/\/next\/dist\/(esm\/)?client\/components\/http-access-fallback\/error-fallback(\.js)?$/, path.join(here, 'lib', 'light-http-error.jsx')],
];
const slashes = (p) => p.split('\\').join('/');

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  /* Light theme only: Next's built-in error page (next/dist/pages/_error) inlines a
     `@media (prefers-color-scheme: dark)` rule. Swap it for lib/light-error.jsx everywhere it is bundled. */
  webpack(config, { webpack }) {
    config.plugins.push(
      new webpack.NormalModuleReplacementPlugin(/_error|error-fallback/, (resolveData) => {
        const cd = resolveData.createData;
        const res = cd && cd.resource;
        if (!res) return;
        const hit = REPLACEMENTS.find(([re]) => re.test(slashes(res)));
        if (!hit) return;
        for (const k of ['request', 'userRequest']) if (typeof cd[k] === 'string') cd[k] = cd[k].split(res).join(hit[1]);
        cd.resource = hit[1];
      }),
    );
    return config;
  },
};
export default nextConfig;
