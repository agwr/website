## Website

- `npm install && uv run compile.py` builds the site into `_site/`: it renders `posts/*.md`, inlines `stylesheets/styles.css`, and minifies every page.
- `npx serve _site` previews the site on http://localhost:3000.
- `git config core.hooksPath .githooks` enables the pre-commit hook, which formats staged HTML and CSS with Prettier.
