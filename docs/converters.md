# Manuals converted without lwarp

Manuals that are not written with PGF's documentation macros (tcolorbox,
tkz-euclide, chemfig, forest, nicematrix, TikZpingus) are converted by a Python converter instead of
lwarp. Such a manual is built from a small set of its own documentation macros
(an example environment, an entry for each command or key, ...), so parsing
its sources directly and mapping these macros onto the tikz.dev HTML structure
(`manualentry`, `entryheadline`, `example`, side tables of contents) gives
cleaner pages than running the manual through lwarp.

## How it works

The shared converter lives in `shared/texhtml/`:

* `core.py`: a scanner for LaTeX sources and the `Converter` class for
  ordinary LaTeX (text, math for MathJax, lists, sections, references,
  citations, footnotes, user macros), code highlighting with links to the
  documented commands and keys, and the chapter loop.
* `site.py`: the tikz.dev page shell, part pages and references, configured by
  a `Manual` (title, parts, footer links, copyright notice).
* `tikzdev-capture.sty` and `extract_images.py`: images.

Everything visual (the output of examples, pictures, boxes in running text)
becomes an image. The converter runs twice: first it collects labels and the
names of documented commands and keys, then it writes the pages. In `tex` mode
it instead writes a copy of the sources in which every visual fragment is
marked with an identifier. LuaLaTeX compiles that copy as usual, but
`tikzdev-capture.sty` also ships each marked fragment as an extra PDF page,
in context, and logs which page holds which fragment. `extract_images.py`
crops these pages and converts them to SVG or PNG; every SVG is compared with
a raster of the PDF page and replaced by the PNG if it renders differently or
is much larger.

Conversion results persist in `build/image-cache/texhtml`, keyed by PDF page
content, resources and the converter/tool versions. Warm runs convert only
missing pages; renumbering captures does not invalidate unchanged pages.
`TIKZ_IMAGE_CACHE` changes the parent cache directory. The top-level build also
reuses compiled captures for frontend-only edits; see [caching.md](caching.md).

## Adding a manual

A manual's folder has its `upstream.lock`, a `build.sh` (instrumented sources,
LuaLaTeX, images, HTML; see `tcolorbox/build.sh`) and `convert.py` with

* a subclass of `texhtml.core.Converter` with handlers `cmd_<name>` and
  `env_<name>` for the manual's own macros, and its additions to the class
  sets of verbatim, transparent and ignored environments and commands and of
  commands that become images;
* the list of chapters `(source file, page name, part)`;
* a `texhtml.site.Manual` and the content of the start page;
* the LaTeX side: usually a small `.sty` that hooks the example environment
  into `tikzdev-capture.sty`: `\HTMLexamplebegin` ... `\HTMLexampleend`
  around the compiled output (see `tcolorbox/tcbhtml.sty`), or
  `\HTMLshipnext{box}` if the example's output is in a box register (see
  `tkz-euclide/tkzhtml.sty`).

Add the manual to `scripts/build.sh` (the case for converted manuals), to the
header menu in `shared/navbar.py` and to the search tags in
`shared/pgfmanual.js`, and give it a header color in `shared/style.css`.

When the way a manual prints something is computed by TeX (forest's index
macros print each name according to its category), the LaTeX run can log the
result for the converter instead of reimplementing it: see
`forest/forhtml.sty`, which logs the printed form of every `\index` call.

Check the result against the official PDF, and look at the converter's
warnings (unknown commands, unresolved references) at the end of each run.
