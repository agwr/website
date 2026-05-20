import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import markdown
from bs4 import BeautifulSoup

WRITING_DIR = Path("writing")


def slugify(title: str) -> str:
    """'Parallel Programming Models' -> 'parallel-programming-models'."""
    slug = title.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    if not slug:
        raise ValueError(f"empty slug derived from title {title!r}")
    return slug

_CODE_RE = re.compile(r"```.*?```|`[^`]*`", re.DOTALL)
_BLOCK_MATH_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$)([^$\n]|\\\$)+(?<!\\)\$")

_MARKDOWN_SYNTAX_RE = re.compile(
    r"!\[[^\]]*\]\([^)]*\)"  # images
    r"|\[[^\]]*\]\([^)]*\)"  # links
    r"|^#{1,6}\s+"  # heading markers
    r"|[*_~`>|]"  # inline formatting markers
    r"|\d+\.\s"  # ordered list markers
    r"|[-*+]\s",  # unordered list markers
    re.MULTILINE | re.DOTALL,
)


def reading_time(md_content: str) -> int:
    """Estimate reading time in minutes from markdown content (≈ 200 wpm)."""
    text = _CODE_RE.sub("", md_content)
    text = _MARKDOWN_SYNTAX_RE.sub(" ", text)
    word_count = len(text.split())
    minutes = max(1, round(word_count / 200))
    return minutes


def has_latex(md_content: str) -> bool:
    without_code = _CODE_RE.sub("", md_content)
    return bool(
        _BLOCK_MATH_RE.search(without_code)
        or _INLINE_MATH_RE.search(without_code)
        or "\\(" in without_code
        or "\\[" in without_code
    )


_FOOTNOTE_REF_RE = re.compile(r"\[(\d+)\]")


def _add_footnotes(html_body: str) -> str:
    """Turn [N] refs into superscript links and anchor the Resources list items."""
    soup = BeautifulSoup(html_body, "html.parser")

    # --- anchor the Resources <ol> items ---
    resources_heading = None
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == "References":
            resources_heading = h2
            break

    if resources_heading:
        ol = resources_heading.find_next_sibling("ol")
        if ol:
            for i, li in enumerate(ol.find_all("li", recursive=False), start=1):
                li["id"] = f"ref-{i}"

    # --- convert [N] refs to superscript links (skip <pre>/<code>) ---
    skip_tags = {"pre", "code"}
    for text_node in list(soup.find_all(string=_FOOTNOTE_REF_RE)):
        if any(p.name in skip_tags for p in text_node.parents):
            continue
        parts = _FOOTNOTE_REF_RE.split(str(text_node))
        if len(parts) == 1:
            continue
        replacement = []
        for j, part in enumerate(parts):
            if j % 2 == 0:
                if j + 1 < len(parts):
                    part = part.rstrip()
                if part:
                    replacement.append(part)
            else:
                sup = soup.new_tag("sup")
                a = soup.new_tag(
                    "a",
                    attrs={"href": f"#ref-{part}", "class": "footnote-ref"},
                )
                a.string = part
                sup.append(a)
                replacement.append(sup)
        text_node.replace_with(*replacement)

    return str(soup)


def render_post(md_path: Path) -> str:
    """Convert raw markdown post content to styled HTML and return as a string."""

    md_content = md_path.read_text(encoding="utf-8")

    html_body = markdown.markdown(md_content, extensions=["fenced_code"])
    html_body = _add_footnotes(html_body)

    mathjax_block = ""
    if has_latex(md_content):
        mathjax_block = """
    <script>
      window.MathJax = {
        tex: {
          inlineMath: [["$", "$"], ["\\\\(", "\\\\)"]],
          displayMath: [["$$", "$$"], ["\\\\[", "\\\\]"]],
        },
        options: {
          skipHtmlTags: ["script", "style", "noscript", "textarea", "pre", "code"],
        },
      };
    </script>
    <script
      id="MathJax-script"
      async
      src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"
    ></script>
"""

    # Wrap in an HTML template. Use root-absolute paths so the template works
    # regardless of how deeply nested the output file is under the site root.
    html_template = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="preload" as="font" type="font/woff" crossorigin
      href="/stylesheets/et-book/et-book-roman-line-figures/et-book-roman-line-figures.woff" />
    <link rel="preload" as="font" type="font/woff" crossorigin
      href="/stylesheets/et-book/et-book-bold-line-figures/et-book-bold-line-figures.woff" />
    <link rel="stylesheet" href="/stylesheets/styles.css" />
    {mathjax_block}
    <title>Ayush Gundawar</title>
  </head>
  <body class="post-page">
    <main class="page-main">
      <article>
        <div class="container">
          {html_body}
        </div>
      </article>
    </main>
  </body>
</html>
"""

    return html_template


def main() -> None:
    md_files = sorted(Path("posts").glob("*.md"))

    # Wipe and rebuild the generated writing directory so renamed/removed posts
    # don't leave stale HTML lying around.
    if WRITING_DIR.exists():
        shutil.rmtree(WRITING_DIR)
    WRITING_DIR.mkdir(parents=True, exist_ok=True)

    # Convert each MD to writing/<slug>/index.html so the URL /writing/<slug>/
    # works on any plain static server (python -m http.server, GitHub Pages,
    # etc.) without needing extension-stripping middleware.
    post_data = []
    seen_slugs: dict[str, Path] = {}
    for md_path in md_files:
        md_content = md_path.read_text(encoding="utf-8")
        lines = md_content.splitlines()

        title = lines[0].lstrip("# ").strip()
        date_str = lines[2].lstrip("> ").strip()
        slug = slugify(title)

        if slug in seen_slugs:
            raise ValueError(
                f"slug collision: {md_path} and {seen_slugs[slug]} both produce {slug!r}"
            )
        seen_slugs[slug] = md_path

        out_dir = WRITING_DIR / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        html_path = out_dir / "index.html"
        html_path.write_text(render_post(md_path), encoding="utf-8")
        subprocess.run(["prettier", "--write", str(html_path)], check=False)

        post_data.append((title, date_str, reading_time(md_content), slug))

    post_data.sort(key=lambda x: datetime.strptime(x[1], "%B %d, %Y"), reverse=True)

    index_path = Path("index.html")
    soup = BeautifulSoup(index_path.read_text(encoding="utf-8"), "html.parser")

    post_links = soup.find(id="post-links")
    if post_links is None:
        raise RuntimeError("No element with id='post-links' found in index.html")
    post_links.clear()

    for title, date_str, read_min, slug in post_data:
        year = str(datetime.strptime(date_str, "%B %d, %Y").year)

        li = soup.new_tag("li")

        link_tag = soup.new_tag(
            "a",
            attrs={"href": f"/writing/{slug}/", "class": "bullet-list_link"},
        )
        link_tag.string = title
        li.append(link_tag)

        meta_span = soup.new_tag("span", attrs={"class": "bullet-list_meta"})
        meta_span.string = f"({year}, {read_min} min)"
        li.append(meta_span)

        post_links.append(li)

    index_path.write_text(str(soup), encoding="utf-8")
    subprocess.run(["prettier", "--write", "index.html"], check=False)


if __name__ == "__main__":
    main()
