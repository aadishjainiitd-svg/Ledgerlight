/** Tailwind is used for a few layout utilities; the design system lives in app/globals.css (ported from the approved mock). */
module.exports = {
  content: ['./app/**/*.{js,jsx}', './components/**/*.{js,jsx}', './lib/**/*.{js,jsx}'],
  corePlugins: { preflight: false },
  theme: { extend: {} },
  plugins: [],
};
