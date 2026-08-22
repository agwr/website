import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, Tag

WRITING_DIR = Path("writing")

# Prettier consults .gitignore unless an explicit ignore path is given, which
# would skip every generated file under the gitignored writing/ directory.
PRETTIER = ["prettier", "--ignore-path", ".prettierignore", "--write"]


def format_html(path: Path) -> None:
    subprocess.run([*PRETTIER, str(path)], check=False)


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
    """Turn inline [N] refs into superscript links and number the Footnotes entries."""
    soup = BeautifulSoup(html_body, "html.parser")

    # --- gather the footnote paragraphs (e.g. <p>[1] Some ref</p>) ---
    ref_entries: set[int] = set()
    references_heading = None
    for h2 in soup.find_all("h2"):
        if h2.get_text(strip=True) == "Footnotes":
            references_heading = h2
            break

    entries: list[tuple[str, Tag]] = []
    if references_heading:
        for sibling in references_heading.next_siblings:
            if sibling.name == "p":
                m = _FOOTNOTE_REF_RE.match(sibling.get_text(strip=True))
                if m:
                    entries.append((m.group(1), sibling))
            elif sibling.name and sibling.name.startswith("h"):
                break

    # --- fold them into a single ordered list ---
    if entries:
        ordered_list = soup.new_tag("ol")

        for position, (number, paragraph) in enumerate(entries, start=1):
            li = soup.new_tag("li")
            li["id"] = f"footnote-{number}"
            # The marker has to match the inline [N] refs, which a post is free
            # to skip or reorder, so pin it whenever it would drift.
            if int(number) != position:
                li["value"] = number

            # Drop the literal "[N] " now that the list renders the marker.
            first_text = paragraph.find(string=_FOOTNOTE_REF_RE)
            if first_text:
                stripped = _FOOTNOTE_REF_RE.sub("", str(first_text), count=1).lstrip()
                first_text.replace_with(stripped)

            for child in list(paragraph.contents):
                li.append(child.extract())

            ordered_list.append(li)
            ref_entries.add(id(li))

        references_heading.insert_after(ordered_list)
        for _, paragraph in entries:
            paragraph.decompose()

    # --- convert [N] refs to superscript links (skip <pre>/<code> and ref paragraphs) ---
    skip_tags = {"pre", "code"}
    for text_node in list(soup.find_all(string=_FOOTNOTE_REF_RE)):
        if any(p.name in skip_tags for p in text_node.parents):
            continue
        if any(id(p) in ref_entries for p in text_node.parents):
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
                a = soup.new_tag("a", attrs={"href": f"#footnote-{part}"})
                a.string = part
                sup.append(a)
                replacement.append(sup)
        text_node.replace_with(*replacement)

    return str(soup)


def _add_title_rule(html_body: str) -> str:
    """Insert an <hr> directly under the post title."""
    soup = BeautifulSoup(html_body, "html.parser")

    h1 = soup.find("h1")
    if h1 is None:
        return html_body
    h1.insert_after(soup.new_tag("hr"))

    return str(soup)


def render_post(md_path: Path) -> str:
    """Convert raw markdown post content to styled HTML and return as a string."""

    md_content = md_path.read_text(encoding="utf-8")

    # The toc extension assigns stable, URL-friendly IDs to headings without
    # rendering a table of contents, enabling links such as "#threading".
    html_body = markdown.markdown(md_content, extensions=["fenced_code", "toc"])
    html_body = _add_footnotes(html_body)
    html_body = _add_title_rule(html_body)

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
    <link rel="stylesheet" href="/stylesheets/styles.css" />
    {mathjax_block}
    <title>Ayush Gundawar</title>
  </head>
  <body>
    {html_body}
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

    # Convert each MD to writing/<slug>.html. The .html is stripped from the URL
    # by the server, so keep every href extensionless (see README for the local
    # preview command that mirrors what GitHub Pages does).
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

        html_path = WRITING_DIR / f"{slug}.html"
        html_path.write_text(render_post(md_path), encoding="utf-8")
        format_html(html_path)

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

        link_tag = soup.new_tag("a", attrs={"href": f"/writing/{slug}"})
        link_tag.string = title
        li.append(link_tag)
        li.append(f" ({year}, {read_min} min)")

        post_links.append(li)

    index_path.write_text(str(soup), encoding="utf-8")
    format_html(index_path)


if __name__ == "__main__":
    main()
