import re
import shutil
import subprocess
from pathlib import Path

import markdown
import minify_html
from bs4 import BeautifulSoup
from hamilton import ad_hoc_utils, driver
from hamilton.htypes import Collect, Parallelizable


def _substitute_once(pattern: str | re.Pattern, replacement: str, html: str) -> str:
    html, count = re.subn(pattern, lambda _: replacement, html)
    if count != 1:
        raise ValueError(f"expected exactly one match for {pattern!r}, found {count}")
    return html


def site_output_dir() -> Path:
    """Recreate an empty output directory for the built site."""
    site = Path("_site")
    shutil.rmtree(site, ignore_errors=True)
    (site / "writing").mkdir(parents=True)
    return site


def site_stylesheet_css() -> str:
    """Read the site-wide stylesheet."""
    return Path("stylesheets/styles.css").read_text()


def post_markdown_path() -> Parallelizable[Path]:
    """Fan out over each Markdown post."""
    yield from Path("posts").glob("*.md")


def post_rendered_html(post_markdown_path: Path, site_stylesheet_css: str) -> str:
    """Render a post's Markdown into a full HTML page with the stylesheet inlined."""
    return """<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <link rel="icon" href="data:,">
    <style>{css}</style>
    <title>Ayush Gundawar</title>
    </head>
    <body><main class="post">{body}</main></body>
    </html>
    """.format(
        css=site_stylesheet_css,
        body=markdown.markdown(
            post_markdown_path.read_text(), extensions=["fenced_code"]
        ),
    )


def post_parsed_parts(post_rendered_html: str) -> dict[str, str]:
    """Split off the title, demoting its heading to an h2, and link up footnotes."""
    soup = BeautifulSoup(post_rendered_html, "html.parser")
    title = soup.h1.text
    soup.h1.name = "h2"

    if heading := soup.find("h2", string="Footnotes"):
        ref = re.compile(r"\s*\[(\d+)\]")
        ol = soup.new_tag("ol")
        heading.insert_after(ol)
        for p in heading.find_next_siblings("p"):
            first = p.find(string=ref)
            n = ref.match(first)[1]
            first.replace_with(ref.sub("", first, 1).lstrip())
            p.name, p["id"], p["value"] = "li", f"footnote-{n}", n
            ol.append(p)

        for text in soup.body.find_all(string=ref):
            if text.find_parent(["pre", "code"]) or ol in text.parents:
                continue
            html = ref.sub(r'<sup><a href="#footnote-\1">\1</a></sup>', text)
            text.replace_with(*BeautifulSoup(html, "html.parser").contents)

    return {"title": title, "html": str(soup)}


def post_typeset_html(post_parsed_parts: dict[str, str]) -> str:
    """Render TeX math to SVG with MathJax, adding its styles to the page head."""
    js = """
    require("mathjax").init({
      loader: { load: ["input/tex", "output/svg"] },
      tex: { inlineMath: [["$", "$"]] },
      svg: { fontCache: "global" },
      startup: { document: require("fs").readFileSync(0, "utf8") },
    }).then(({ startup: { adaptor, document } }) => {
      const html = document.document;
      if ([...document.math].length === 0) {
        adaptor.remove(adaptor.elementById(adaptor.head(html), "MJX-SVG-styles"));
        adaptor.remove(adaptor.elementById(adaptor.body(html), "MJX-SVG-global-cache"));
      }
      process.stdout.write(adaptor.doctype(html) + adaptor.outerHTML(adaptor.root(html)));
    });
    """
    return subprocess.check_output(
        ["node", "-e", js], input=post_parsed_parts["html"], text=True
    )


def post_page_file(
    post_parsed_parts: dict[str, str], post_typeset_html: str
) -> tuple[Path, str]:
    """Pair the post's page with its output path, slugged from the title."""
    slug = re.sub(r"[^a-z0-9]+", "-", post_parsed_parts["title"].lower()).strip("-")
    return Path("writing") / f"{slug}.html", post_typeset_html


def post_page_files(
    post_page_file: Collect[tuple[Path, str]],
) -> list[tuple[Path, str]]:
    """Collect every post's page."""
    return list(post_page_file)


def handwritten_page_files(site_stylesheet_css: str) -> list[tuple[Path, str]]:
    """Read the hand-written HTML pages with their stylesheet link inlined."""
    link = r'<link rel="stylesheet" href="/stylesheets/styles.css"\s*/?>'
    style = f"<style>{site_stylesheet_css}</style>"
    return [
        (path, _substitute_once(link, style, path.read_text()))
        for path in [Path("index.html"), Path("internet.html")]
    ]


def page_file(
    post_page_files: list[tuple[Path, str]],
    handwritten_page_files: list[tuple[Path, str]],
) -> Parallelizable[tuple[Path, str]]:
    """Fan out over every page on the site, posts included."""
    yield from post_page_files + handwritten_page_files


def page_prerendering_html(page_file: tuple[Path, str]) -> str:
    """Add speculation rules so links are prerendered before they're clicked."""
    return _substitute_once(
        "</head>",
        '<script type="speculationrules">'
        '{"prerender": [{"where": {"href_matches": "/*"}, "eagerness": "moderate"}],'
        ' "prefetch": [{"where": {"not": {"href_matches": "/*"}}, "eagerness": "moderate"}]}'
        "</script></head>",
        page_file[1],
    )


def page_minified_html(page_prerendering_html: str) -> str:
    """Minify the page's HTML and inline CSS."""
    return minify_html.minify(page_prerendering_html, minify_css=True)


def page_output_path(
    site_output_dir: Path, page_file: tuple[Path, str], page_minified_html: str
) -> Path:
    """Write the finished page into the site directory."""
    output = site_output_dir / page_file[0]
    output.write_text(page_minified_html)
    return output


def site_output_paths(page_output_path: Collect[Path]) -> list[Path]:
    """Every file in the built site."""
    return list(page_output_path)


# Hamilton wires these transformations into a graph by matching each parameter name
# to the transformation of the same name, then runs whatever site_output_paths needs.
# Parallelizable and Collect fan out over each post and page and gather the results.
transformations = ad_hoc_utils.create_temporary_module(
    site_output_dir,
    site_stylesheet_css,
    post_markdown_path,
    post_rendered_html,
    post_parsed_parts,
    post_typeset_html,
    post_page_file,
    post_page_files,
    handwritten_page_files,
    page_file,
    page_prerendering_html,
    page_minified_html,
    page_output_path,
    site_output_paths,
)
driver.Builder().enable_dynamic_execution(allow_experimental_mode=True).with_modules(
    transformations
).build().execute(["site_output_paths"])
