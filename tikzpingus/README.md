# TikZpingus manual

The HTML version of [TikZpingus](https://github.com/EagleoutIce/tikzpingus)
for `tikz.dev/tikzpingus/`, using the shared Python converter and native
LuaLaTeX illustration capture.

```bash
scripts/fetch.sh tikzpingus
scripts/build.sh tikzpingus
scripts/serve.py          # http://127.0.0.1:8765/tikzpingus/
```

Inside this folder, `./build.sh images` re-extracts the last compilation's
illustrations and `./build.sh html` regenerates only the pages. Requirements
are the standard TeX Live, Python and image tools used by the other converted
manuals. The build uses the pinned `tex/tikzpingus.sty`, with glows enabled.

The adapter maps the manual's `keyexplain`, `subkeyexplain`,
`showkeyexplain` and command environments to HTML definitions. Compact
`keyline`/`subkeyline` declarations retain their generated executable examples.
`pinguhtml.sty` captures the output of `tcblisting` in document order and logs
computed defaults and lengths for the converter. Examples compile in the same
process, without upstream's externalization or shell escape. The PDF-only
`xlistings` and `code-link` dependencies are replaced with standard listings;
no Git submodule is required.

The guide is split by subsection and the full reference by gadget or component.
The visual overviews use individual images with links to the corresponding
definitions. The key index includes aliases and generated shortcuts. Internal
source excerpts and their line numbers come directly from region/chunk markers
in the pinned package; source links use that exact revision. The print cover,
page furniture and page-number indices are replaced by the shared site layout.

The image pipeline checks SVG output against the PDF and uses PNG when the
SVG differs or is disproportionately large. The converter fails on missing
illustrations or unresolved conversion warnings, and the normal build validates
local links, anchors and image dimensions before publishing its local result.

The lock participates in normal upstream watching, caching and deployment.
The production Algolia crawler configuration includes `/tikzpingus/`; apply
that configuration and crawl after deploying to populate production search.

## Start-page editor

The SVG parts editor is part of `/tikzpingus/`, between the compact package
title and Contents, using the shared manual header, navigation and footer.
The manual's HTML conversion installs its markup and assets automatically:

```bash
scripts/build.sh tikzpingus
scripts/serve.py 8767
# http://127.0.0.1:8767/tikzpingus/
node --test tikzpingus/editor/core.test.mjs
```

Once the manual exists in `build/tikzpingus/site/`, running
`python3 tikzpingus/editor/build.py` updates just the editor markup and assets
in that built manual. `editor/editor.html` is an HTML fragment; its stylesheet
is scoped to `#pingu-editor`, with additional rules for the compact title box.
The `editor/` asset folder has no separate HTML entry page or redirect.
Commands, keys and named styles in the generated code link to their manual
entries. Inspector headings have documentation links that follow the current
selection. These links open in a new tab and are resolved from the generated
key index, with target files and anchors checked during the build. PNG/SVG
downloads are in the editor toolbar.

The runtime is plain JavaScript with no external dependencies. `catalog.json`
defines the supported choices. The build compiles an instrumented disposable
copy of the pinned package with `latex` and converts it with `dvisvgm`. Paths,
shadings and typeset glyphs retain their part and PGF layer; clipping and font
resources are extracted alongside them. Clothes preserve their behind/middle/
front drawing phases. Libraries are generated for each supported body shape. Only
the selected body's library loads, with small separate body thumbnails.
Native compilations and extracted libraries are cached under
`build/tikzpingus/editor/`; `--force` regenerates the extracted libraries.
Ghostscript's shared library is detected automatically, or supplied as `LIBGS`.

The editor exports transparent SVG/PNG and TikZ snippets or complete documents.
SVG and PNG exports are composed and measured from a snapshot of the settings,
independently of the animated preview, so exporting during a transition uses
the same final framing as exporting after it finishes.
It saves the latest settings locally and encodes share links in the URL
fragment, with session undo/redo. New `#v2=` links store only changes from a
frozen default, with stable option codes, palette codes, and compact hex colors.
A crown alone is `#v2=h4`; a crown with the Ocean palette is `#v2=h4.p3`.
Existing `#v1=` JSON links still open. Share code positions must not be
reordered when the catalog or palette UI changes.
Favorites are kept in local storage. Choice tiles preview the current penguin
with that choice applied. Change animations depend on the part that changed. The ground shadow and
idle animations in the preview are marked `data-decor` and dropped from exports. Held items use the grab pose; selecting another pose clears that
item. The catalog includes three bodies, expressions, both wing poses,
feet, bills, headwear, eyewear, neckwear and selected extras. Clothes include a
buttoned shirt, sweater and cape; headphones, microphones, guitars and laptops
join the accessory and held-item choices. The Musician and At work presets
demonstrate these combinations. It covers the
listed choices, rather than interpreting arbitrary TeX or every package key.

For native fidelity checks, run `editor/capture-fixtures.js` with Playwright's
`browser_run_code_unsafe` on the built page, then save `window.editorFixtures`
as JSON with `browser_evaluate`. Run
`python3 tikzpingus/editor/verify.py <fixtures.json>` to independently compile
the exported code with the unmodified pinned package and compare rasterized
SVGs. Reports, original TeX, native SVGs and raster pairs are retained under
`build/tikzpingus/editor/verification/`.

`editor/check-export-framing.js`, run with the same Playwright tool, compares
actual SVG and PNG downloads made during and after a tall-headwear transition.
It uses an isolated browser context and checks that both downloads are identical.

Share links use the manual's start-page URL. Other manual fragments, such as
footnote links, do not affect the editor. Its controls are marked
`data-nosnippet` to keep them out of documentation search records.
To publish the integrated editor, deploy the TikZpingus package output,
including its start page and `editor/` assets; no other manual needs uploading.
