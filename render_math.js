// Typeset the HTML body on stdin with MathJax; writes {style, body} as JSON.
require("mathjax")
  .init({
    loader: { load: ["input/tex", "output/svg"] },
    tex: { inlineMath: [["$", "$"]] },
    svg: { fontCache: "global" },
    startup: { document: require("fs").readFileSync(0, "utf8") },
  })
  .then(({ startup: { adaptor, document }, svgStylesheet }) => {
    const body = adaptor.body(document.document);
    const hasMath = [...document.math].length > 0;
    if (!hasMath) adaptor.remove(adaptor.elementById(body, "MJX-SVG-global-cache"));
    process.stdout.write(
      JSON.stringify({
        style: hasMath ? `<style>${adaptor.textContent(svgStylesheet())}</style>` : "",
        body: adaptor.innerHTML(body),
      }),
    );
  });
