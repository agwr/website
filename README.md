## Website

Build (renders `posts/*.md` into minified HTML under `writing/`; needs
`prettier` on PATH to format the committed pages). Math is typeset to SVG at
build time by MathJax via `render_math.js`, and `stylesheets/styles.css` is
inlined into every page, so edit the CSS there and rebuild:

```sh
npm install
uv run compile.py
```

Preview on http://localhost:3000:

```sh
npx serve
```

Internal links must be root-absolute and extensionless (`/writing/<slug>`), so
`serve` matches how GitHub Pages resolves them.
