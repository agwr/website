import re
import subprocess
from datetime import datetime
from pathlib import Path

import markdown
from bs4 import BeautifulSoup
from pygments.formatters import HtmlFormatter

_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_BLOCK_MATH_RE = re.compile(r"\$\$.*?\$\$", re.DOTALL)
_INLINE_MATH_RE = re.compile(r"(?<!\\)\$(?!\$)([^$\n]|\\\$)+(?<!\\)\$")


_MARKDOWN_SYNTAX_RE = re.compile(
    r"```.*?```"  # fenced code blocks
    r"|`[^`]*`"  # inline code
    r"|!\[[^\]]*\]\([^)]*\)"  # images
    r"|\[[^\]]*\]\([^)]*\)"  # links (keep link text via sub below)
    r"|^#{1,6}\s+"  # heading markers
    r"|[*_~`>|]"  # inline formatting markers
    r"|\d+\.\s"  # ordered list markers
    r"|[-*+]\s",  # unordered list markers
    re.MULTILINE | re.DOTALL,
)


def reading_time(md_content: str) -> int:
    """Estimate reading time in minutes from markdown content (≈ 200 wpm)."""
    # Strip code blocks and markdown syntax to get prose words
    text = _FENCED_CODE_RE.sub("", md_content)
    text = _MARKDOWN_SYNTAX_RE.sub(" ", text)
    word_count = len(text.split())
    minutes = max(1, round(word_count / 200))
    return minutes


def has_latex(md_content: str) -> bool:
    without_code = _FENCED_CODE_RE.sub("", md_content)
    without_code = _INLINE_CODE_RE.sub("", without_code)

    return bool(
        _BLOCK_MATH_RE.search(without_code)
        or _INLINE_MATH_RE.search(without_code)
        or "\\(" in without_code
        or "\\)" in without_code
        or "\\[" in without_code
        or "\\]" in without_code
    )


def render_post(md_path: Path) -> str:
    """Convert raw markdown post content to styled HTML and return as a string."""

    # Read the markdown file
    md_content = md_path.read_text(encoding="utf-8")

    # Convert to HTML using markdown with code highlighting extensions include fenced_code
    # and codehilite for syntax highlighting
    html_body = markdown.markdown(md_content, extensions=["fenced_code", "codehilite"])

    # Create Pygments CSS
    formatter = HtmlFormatter(style="arduino")
    css_code_highlighting = formatter.get_style_defs(".codehilite")
    css_code_highlighting = css_code_highlighting.replace("bold", "normal")
    css_code_highlighting = css_code_highlighting.replace("italic", "normal")

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
    <link rel="stylesheet" href="../../stylesheets/styles.css" />
    <style>
      {css_code_highlighting}
      .codehilite {{ background: transparent; }}
    </style>
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


def render_writing() -> None:
    """Render the post listing in index.html."""

    md_files = sorted(Path("posts/markdown").rglob("*.md"))

    # Extract post data (title, date, reading time, corresponding html file name)
    post_data = []
    for md_file_path in md_files:
        md_content = md_file_path.read_text(encoding="utf-8")
        lines = md_content.splitlines()

        # First line: # Title
        # Second line: > Month DD, YYYY
        title_line = lines[0].lstrip("# ").strip()
        date_line = lines[2].lstrip("> ").strip()
        read_min = reading_time(md_content)

        # Corresponding HTML file name
        html_name = md_file_path.with_suffix(".html").name
        post_data.append((title_line, date_line, read_min, html_name))

    # Sort posts by date descending (newest first)
    post_data.sort(key=lambda x: datetime.strptime(x[1], "%B %d, %Y"), reverse=True)

    # Modify index.html
    index_html_path = Path("index.html")
    soup = BeautifulSoup(index_html_path.read_text(encoding="utf-8"), "html.parser")

    # Find the div for post links
    post_links_div = soup.find(id="post-links")
    if post_links_div is None:
        raise RuntimeError("No element with id='post-links' found in index.html")

    # Clear existing content
    post_links_div.clear()  # type: ignore

    # Add each post as a row with year, title, and reading time
    for title, date_str, read_min, html_name in post_data:
        parsed_date = datetime.strptime(date_str, "%B %d, %Y")
        year = str(parsed_date.year)

        # Create a link row
        link_tag = soup.new_tag(
            "a", href=f"posts/html/{html_name}", **{"class": "post-row"}
        )

        # Year span
        year_span = soup.new_tag("span", **{"class": "post-year"})
        year_span.string = year
        link_tag.append(year_span)

        # Title span
        title_span = soup.new_tag("span", **{"class": "post-title"})
        title_span.string = title
        link_tag.append(title_span)

        # Reading time span
        duration_span = soup.new_tag("span", **{"class": "post-duration"})
        duration_span.string = f"{read_min} min"
        link_tag.append(duration_span)

        post_links_div.append(link_tag)

    # Write the updated index.html
    index_html_path.write_text(str(soup), encoding="utf-8")


def main() -> None:
    # Ensure output directory exists
    html_output_dir = Path("posts/html")
    html_output_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(Path("posts/markdown").rglob("*.md"))

    # Convert each MD to HTML
    for md_file_path in md_files:
        html_content = render_post(md_file_path)
        html_file_path = html_output_dir / md_file_path.with_suffix(".html").name
        html_file_path.write_text(html_content, encoding="utf-8")
        subprocess.run(["prettier", "--write", str(html_file_path)], check=False)

    # Update the writing listing on the homepage
    render_writing()
    subprocess.run(["prettier", "--write", "index.html"], check=False)


if __name__ == "__main__":
    main()
