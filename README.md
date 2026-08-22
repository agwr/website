## Website

Build (renders `posts/*.md` into `writing/`, needs `prettier` on PATH):

```sh
uv run compile.py
```

Preview on http://localhost:3000:

```sh
npx serve
```

Internal links must be root-absolute and extensionless (`/writing/<slug>`), so
`serve` matches how GitHub Pages resolves them.
