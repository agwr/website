import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import markdown
import minify_html
from bs4 import BeautifulSoup

WRITING_DIR = Path("writing")
INDEX = Path("index.html")
PAGES = [INDEX, Path("internet.html")]
CSS = Path("stylesheets/styles.css").read_text(encoding="utf-8")

_CODE_RE = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)
_MARKDOWN_SYNTAX_RE = re.compile(
    r"!?\[[^\]]*\]\([^)]*\)|^#{1,6}\s+|[*_~`>|]|\d+\.\s|[-*+]\s", re.MULTILINE
)
_FOOTNOTE_REF_RE = re.compile(r"\[(\d+)\]")

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <style>{css}</style>
    {style}
    <title>Ayush Gundawar</title>
  </head>
  <body>
    {body}
  </body>
</html>
"""


def slugify(title: str) -> str:
    """'Parallel Programming Models' -> 'parallel-programming-models'."""
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")


def reading_time(md: str) -> int:
    """Estimate reading time in minutes (≈ 200 wpm)."""
    words = _MARKDOWN_SYNTAX_RE.sub(" ", _CODE_RE.sub("", md)).split()
    return max(1, round(len(words) / 200))


def _add_footnotes(soup: BeautifulSoup) -> None:
    """Turn inline [N] refs into superscript links and number the Footnotes entries."""
    ol = soup.new_tag("ol")
    heading = soup.find("h2", string="Footnotes")
    for p in heading.find_next_siblings() if heading else ():
        if p.name.startswith("h"):
            break
        m = p.name == "p" and _FOOTNOTE_REF_RE.match(p.get_text(strip=True))
        if not m:
            continue
        li = soup.new_tag("li", id=f"footnote-{m[1]}")
        if int(m[1]) != len(ol.contents) + 1:
            li["value"] = m[1]
        first = p.find(string=_FOOTNOTE_REF_RE)
        first.replace_with(_FOOTNOTE_REF_RE.sub("", first, count=1).lstrip())
        li.extend(p)
        p.decompose()
        ol.append(li)
    if ol.contents:
        heading.insert_after(ol)

    for text in soup.find_all(string=_FOOTNOTE_REF_RE):
        if any(t is ol or t.name in ("pre", "code") for t in text.parents):
            continue
        parts = _FOOTNOTE_REF_RE.split(text)
        out = []
        for i, part in enumerate(parts):
            if i % 2:
                sup = soup.new_tag("sup")
                sup.append(soup.new_tag("a", href=f"#footnote-{part}"))
                sup.a.string = part
                out.append(sup)
            else:
                if i + 1 < len(parts):
                    part = part.rstrip()
                if part:
                    out.append(part)
        text.replace_with(*out)


def render_post(md: str) -> str:
    soup = BeautifulSoup(
        markdown.markdown(md, extensions=["fenced_code", "toc"]), "html.parser"
    )
    _add_footnotes(soup)
    soup.h1.insert_after(soup.new_tag("hr"))
    # Typeset math at build time so the page never reflows while MathJax loads.
    typeset = subprocess.check_output(["node", "render_math.js"], input=str(soup), text=True)
    html = TEMPLATE.format(css=CSS, **json.loads(typeset))
    return minify_html.minify(html, minify_css=True)


def main() -> None:
    shutil.rmtree(WRITING_DIR, ignore_errors=True)
    WRITING_DIR.mkdir()

    posts = []
    for md_path in sorted(Path("posts").glob("*.md")):
        md = md_path.read_text(encoding="utf-8")
        title, _, date = md.splitlines()[:3]
        title = title.lstrip("# ").strip()
        date = datetime.strptime(date.lstrip("> ").strip(), "%B %d, %Y")
        slug = slugify(title)
        (WRITING_DIR / f"{slug}.html").write_text(render_post(md), encoding="utf-8")
        posts.append((date, title, slug, reading_time(md)))

    pages = {p: BeautifulSoup(p.read_text(encoding="utf-8"), "html.parser") for p in PAGES}
    for soup in pages.values():
        soup.find("style", id="css").string = CSS

    index = pages[INDEX]
    links = index.find(id="post-links")
    links.clear()
    for date, title, slug, minutes in sorted(posts, key=lambda p: p[0], reverse=True):
        li = index.new_tag("li")
        li.append(index.new_tag("a", href=f"/writing/{slug}"))
        li.a.string = title
        li.append(f" ({date.year}, {minutes} min)")
        links.append(li)

    for path, soup in pages.items():
        path.write_text(str(soup), encoding="utf-8")
    subprocess.run(["prettier", "--write", *PAGES])


if __name__ == "__main__":
    main()
