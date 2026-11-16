import json
import re
import shutil
import subprocess
from pathlib import Path

import markdown
import minify_html
from bs4 import BeautifulSoup

POSTS, SITE = Path("posts"), Path("_site")
PAGES = [Path("index.html"), Path("internet.html")]
STATIC = [Path("CNAME")]
CSS = Path("stylesheets/styles.css").read_text()
STYLESHEET_LINK = re.compile(r'<link rel="stylesheet" href="/stylesheets/styles.css"\s*/?>')
SPECULATION_RULES = (
    '{"prerender": [{"where": {"href_matches": "/*"}, "eagerness": "moderate"}],'
    ' "prefetch": [{"where": {"not": {"href_matches": "/*"}}, "eagerness": "moderate"}]}'
)


REF = re.compile(r"\s*\[(\d+)\]")


def footnotes(soup: BeautifulSoup) -> None:
    heading = soup.find("h2", string="Footnotes")
    if not heading:
        return

    ol = soup.new_tag("ol")
    heading.insert_after(ol)
    for p in heading.find_next_siblings("p"):
        first = p.find(string=REF)
        n = REF.match(first)[1]
        first.replace_with(REF.sub("", first, 1).lstrip())
        p.name, p["id"], p["value"] = "li", f"footnote-{n}", n
        ol.append(p)

    for text in soup.find_all(string=REF):
        if text.find_parent(["pre", "code"]) or ol in text.parents:
            continue
        html = REF.sub(r'<sup><a href="#footnote-\1">\1</a></sup>', text)
        text.replace_with(*BeautifulSoup(html, "html.parser").contents)


def typeset(html: str) -> dict[str, str]:
    js = """
    require("mathjax").init({
      loader: { load: ["input/tex", "output/svg"] },
      tex: { inlineMath: [["$", "$"]] },
      svg: { fontCache: "global" },
      startup: { document: require("fs").readFileSync(0, "utf8") },
    }).then(({ startup: { adaptor, document }, svgStylesheet }) => {
      const body = adaptor.body(document.document);
      const hasMath = [...document.math].length > 0;
      if (!hasMath) adaptor.remove(adaptor.elementById(body, "MJX-SVG-global-cache"));
      process.stdout.write(JSON.stringify({
        style: hasMath ? `<style>${adaptor.textContent(svgStylesheet())}</style>` : "",
        body: adaptor.innerHTML(body),
      }));
    });
    """
    return json.loads(
        subprocess.check_output(["node", "-e", js], input=html, text=True)
    )


def render(md: str) -> tuple[str, str]:
    soup = BeautifulSoup(
        markdown.markdown(md, extensions=["fenced_code"]), "html.parser"
    )
    title = soup.h1.text
    soup.h1.name = "h2"
    footnotes(soup)

    page = """<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:,">
    <link rel="stylesheet" href="/stylesheets/styles.css">
    {style}
    <title>Ayush Gundawar</title>
    </head>
    <body><main class="post">{body}</main></body>
    </html>
    """.format(**typeset(str(soup)))
    return page, title


def substitute_once(pattern: str | re.Pattern, replacement: str, html: str) -> str:
    html, count = re.subn(pattern, lambda _: replacement, html)
    if count != 1:
        raise ValueError(f"expected exactly one match for {pattern!r}, found {count}")
    return html


def finalize(html: str) -> str:
    html = substitute_once(STYLESHEET_LINK, f"<style>{CSS}</style>", html)
    html = substitute_once(
        "</head>",
        f'<script type="speculationrules">{SPECULATION_RULES}</script></head>',
        html,
    )
    return minify_html.minify(html, minify_css=True)


def main() -> None:
    shutil.rmtree(SITE, ignore_errors=True)
    (SITE / "writing").mkdir(parents=True)
    for path in POSTS.glob("*.md"):
        html, title = render(path.read_text())
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        (SITE / "writing" / f"{slug}.html").write_text(finalize(html))

    for path in PAGES:
        (SITE / path).write_text(finalize(path.read_text()))
    for path in STATIC:
        shutil.copy(path, SITE / path)


if __name__ == "__main__":
    main()
