import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import markdown
import minify_html
from bs4 import BeautifulSoup

POSTS, WRITING = Path("posts"), Path("writing")
INDEX, PAGES = Path("index.html"), [Path("index.html"), Path("internet.html")]
CSS = Path("stylesheets/styles.css").read_text()
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


def render(md: str) -> tuple[str, str, datetime, int]:
    soup = BeautifulSoup(
        markdown.markdown(md, extensions=["fenced_code", "toc"]), "html.parser"
    )
    title = soup.h1.text
    date = datetime.strptime(soup.blockquote.text.strip(), "%B %d, %Y")
    soup.h1.name = "h2"
    footnotes(soup)

    page = """<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>{css}</style>
    {style}
    <script type="speculationrules">{rules}</script>
    <title>Ayush Gundawar</title>
    </head>
    <body>{body}</body>
    </html>
    """.format(css=CSS, rules=SPECULATION_RULES, **typeset(str(soup)))
    html = minify_html.minify(page, minify_css=True)

    for pre in soup("pre"):
        pre.decompose()
    minutes = max(1, round(len(soup.text.split()) / 200))
    return html, title, date, minutes


def main() -> None:
    shutil.rmtree(WRITING, ignore_errors=True)
    WRITING.mkdir()
    posts = []
    for path in POSTS.glob("*.md"):
        html, title, date, minutes = render(path.read_text())
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        (WRITING / f"{slug}.html").write_text(html)
        posts.append((date, title, slug, minutes))

    pages = {p: BeautifulSoup(p.read_text(), "html.parser") for p in PAGES}
    for soup in pages.values():
        soup.find("style", id="css").string = CSS
        soup.find("script", type="speculationrules").string = SPECULATION_RULES

    index = pages[INDEX]
    links = index.find(id="post-links")
    links.clear()
    for date, title, slug, minutes in sorted(posts, reverse=True):
        li = index.new_tag("li")
        li.append(index.new_tag("a", href=f"/writing/{slug}"))
        li.a.string = title
        li.append(f" ({date.year}, {minutes} min)")
        links.append(li)

    for path, soup in pages.items():
        path.write_text(str(soup))
    subprocess.run(["prettier", "--write", *PAGES])


if __name__ == "__main__":
    main()
