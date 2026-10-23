import json
import re
import shutil
import subprocess
from pathlib import Path

import markdown
import minify_html
from bs4 import BeautifulSoup

POSTS, WRITING = Path("posts"), Path("writing")
PAGES = [Path("index.html"), Path("internet.html")]
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
    <style>{css}</style>
    {style}
    <script type="speculationrules">{rules}</script>
    <title>Ayush Gundawar</title>
    </head>
    <body><main class="post">{body}</main></body>
    </html>
    """.format(css=CSS, rules=SPECULATION_RULES, **typeset(str(soup)))
    return minify_html.minify(page, minify_css=True), title


def main() -> None:
    shutil.rmtree(WRITING, ignore_errors=True)
    WRITING.mkdir()
    for path in POSTS.glob("*.md"):
        html, title = render(path.read_text())
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
        (WRITING / f"{slug}.html").write_text(html)

    for path in PAGES:
        soup = BeautifulSoup(path.read_text(), "html.parser")
        soup.find("style", id="css").string = CSS
        soup.find("script", type="speculationrules").string = SPECULATION_RULES
        path.write_text(str(soup))
    subprocess.run(["prettier", "--write", *PAGES])


if __name__ == "__main__":
    main()
