import re
import subprocess
from datetime import datetime
from pathlib import Path

import markdown
from bs4 import BeautifulSoup, NavigableString

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


def add_smallcaps(html_body: str, num_words: int = 1) -> str:
    """Wrap the first `num_words` words of the opening paragraph in smallcaps."""
    soup = BeautifulSoup(html_body, "html.parser")

    # Find the first <p> that is a direct child (not inside a blockquote)
    first_p = None
    for p in soup.find_all("p"):
        if p.find_parent("blockquote") is None:
            first_p = p
            break

    if first_p is None:
        return html_body

    # Find the first text node in the paragraph (may have inline elements like <a>)
    first_text = None
    for child in first_p.children:
        if isinstance(child, NavigableString) and child.strip():
            first_text = child
            break

    if first_text is None:
        return html_body

    text = str(first_text)
    words = text.split(None, num_words)
    if len(words) <= num_words:
        return html_body

    # Build: <span class="smallcaps">first words</span> rest of text
    leading = " ".join(words[:num_words])
    rest = text[len(leading) :]

    span = soup.new_tag("span", attrs={"class": "smallcaps"})
    span.string = leading
    first_text.replace_with(span)
    span.insert_after(rest)

    return str(soup)


def render_post(md_path: Path) -> str:
    """Convert raw markdown post content to styled HTML and return as a string."""

    # Read the markdown file
    md_content = md_path.read_text(encoding="utf-8")

    # Convert to HTML using markdown with fenced_code extension
    html_body = markdown.markdown(md_content, extensions=["fenced_code"])

    # Add smallcaps to the opening word of the first paragraph
    html_body = add_smallcaps(html_body)

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

    # Wrap in an HTML template
    html_template = f"""
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="stylesheet" href="../stylesheets/styles.css" />
    {mathjax_block}
    <title>Ayush Gundawar</title>
  </head>
  <body>
    <div class="container">
      <main>
        {html_body}
      </main>
    </div>
  </body>
</html>
"""

    return html_template


def main() -> None:
    md_files = sorted(Path("posts").glob("*.md"))

    # Convert each MD to HTML and collect post metadata in one pass
    post_data = []
    for md_path in md_files:
        md_content = md_path.read_text(encoding="utf-8")
        lines = md_content.splitlines()

        # Render post HTML
        html_path = md_path.with_suffix(".html")
        html_path.write_text(render_post(md_path), encoding="utf-8")
        subprocess.run(["prettier", "--write", str(html_path)], check=False)

        # Collect metadata for index listing
        title = lines[0].lstrip("# ").strip()
        date_str = lines[2].lstrip("> ").strip()
        post_data.append((title, date_str, reading_time(md_content), html_path.name))

    # Sort posts by date descending (newest first)
    post_data.sort(key=lambda x: datetime.strptime(x[1], "%B %d, %Y"), reverse=True)

    # Update index.html post listing
    index_path = Path("index.html")
    soup = BeautifulSoup(index_path.read_text(encoding="utf-8"), "html.parser")

    post_links_div = soup.find(id="post-links")
    if post_links_div is None:
        raise RuntimeError("No element with id='post-links' found in index.html")
    post_links_div.clear()

    for title, date_str, read_min, html_name in post_data:
        year = str(datetime.strptime(date_str, "%B %d, %Y").year)

        link_tag = soup.new_tag(
            "a", attrs={"href": f"posts/{html_name}", "class": "post-row"}
        )

        year_span = soup.new_tag("span", attrs={"class": "post-year"})
        year_span.string = year
        link_tag.append(year_span)

        title_span = soup.new_tag("span", attrs={"class": "post-title"})
        title_span.string = title
        link_tag.append(title_span)

        duration_span = soup.new_tag("span", attrs={"class": "post-duration"})
        duration_span.string = f"{read_min} min"
        link_tag.append(duration_span)

        post_links_div.append(link_tag)

    index_path.write_text(str(soup), encoding="utf-8")
    subprocess.run(["prettier", "--write", "index.html"], check=False)


if __name__ == "__main__":
    main()
