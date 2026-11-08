# Building the manuals

## Sources

Each manual pins an upstream revision in `<package>/upstream.lock` (`repo`,
`commit`, the `watch` paths that trigger a rebuild, the documentation folder
`docdir`, and the `sitepath` on tikz.dev). wheelchart, tkz-euclide and chemfig are
fetched from archives instead of Git: their `upstream.json` pins the archives
by checksum (see [wheelchart/README.md](../wheelchart/README.md) and
[tkz-euclide/README.md](../tkz-euclide/README.md)).

```bash
scripts/fetch.sh pgf               # checkout at the pinned commit, in .upstream/pgf
scripts/fetch.sh pgf origin/master # try another revision without changing the pin
scripts/prepare.py pgf             # only assemble the source tree build/pgf/src
scripts/build.sh pgf               # prepare, run LaTeX and postprocessing -> build/pgf/site
```

`prepare.py` copies the upstream tree, runs `<package>/preprocess.py` if there
is one, applies `<package>/patches/`, and adds the package's own files and
`shared/`. Manuals whose lock says `documentation=pgf` (those written with
PGF's documentation macros) also get the HTML versions of those macros from
`shared/pgfmanual/`. LaTeX runs with the package code of the pinned commit
ahead of the version in TeX Live, so the manual describes the code it is
compiled with.

`scripts/build.sh` refuses to publish a site whose LaTeX run failed or that
has no `index.html`. The manuals processed by `shared/pgf_contrib_site.py`
are also checked by `shared/check_manual_site.py` (missing files, broken
anchors, missing image dimensions, unresolved references), as are tcolorbox,
tkz-euclide and chemfig before their sites are published. To check a built
manual directly, run `python3 shared/check_manual_site.py build/<package>/site`.

Successful builds cache the compiled inputs. A subsequent frontend-only change
reruns HTML processing and checks while skipping LaTeX and image conversion.
Set `TIKZ_COMPILED_CACHE_ENABLED=0` to force a full build. Illustration
conversion also has a persistent content cache, including for the Python
manuals. See [caching.md](caching.md) for keys, review rules and cache controls.

## Fixing a patch

When upstream changes a place one of the patches touches, the build stops
with "patch X does not apply":

```bash
scripts/fetch.sh pgf <new-commit>
scripts/prepare.py pgf --reject      # applies what it can, leaves *.rej files
# edit the files named by the .rej files in build/pgf/src by hand, then
scripts/prepare.py pgf --refresh-patches build/pgf/src
```

`--refresh-patches` rewrites `pgf/patches/` from the edited tree. Commit it
together with the new commit in `pgf/upstream.lock`.

## Frontend

All manuals use `shared/style.css` and `shared/pgfmanual.js`. Each build sets
a class on `<html>` that selects package-specific rules: `.pkg-pgf`,
`.pkg-pgfplots`, `.pkg-tcolorbox`, and so on. The manuals other than PGF,
PGFplots and tcolorbox also have `.pkg-pgf-contrib` and share their page
processing in `shared/pgf_contrib_site.py`. The list of manuals in the header
menu is in `shared/navbar.py`. Local CSS and JavaScript URLs carry content
hashes, so browsers pick up new versions immediately.

The start pages share one design (`shared/home.py`): the title box of the PGF
and PGFplots start pages, the abstract, a row of example pictures, and the
contents as cards accented in the manual's color (`--pkg-color` in
`style.css`). The pictures are chosen by hand per manual (`SHOWCASE` in a
converter, `showcase` in an lwarp manual's `Manual`), each by its page and a
fragment of its code, so that they survive renumbering; one that is no longer
found is left out. The converted manuals build
it in their `home_html`; for the lwarp manuals, `pgf_contrib_site.py` replaces
lwarp's title page and table of contents with it, taking the title, logo and
version from the title page and the author from the `Manual`.

Search uses DocSearch v3 (`shared/docsearch.py`, initialised in
`pgfmanual.js`) with the Algolia application `JS6V5VZSDB` and index `tikz`.
Each manual filters by its own tag (PGF: `tikz`, the others: their package
name); a switch in the search window searches all manuals instead. Both
scopes send one query, requesting ten groups with up to two hits per group.

The production crawler configuration is kept in `scripts/algolia-crawler.js`
and published through the Algolia crawler editor. Retain the editor's existing
crawler API key when copying it; the repository contains only a placeholder.
The crawler starts at the manuals' root URLs and excludes `/monorepo/`
and the independent tools on the domain. It assigns each record its manual's
tag and a `search_group`: the enclosing `h6` anchor, falling back to `h5`,
`h4`, or the page URL. Definition entries retain their own result links while
sharing the enclosing subsection's result allowance. Examples and navigation
are excluded from the indexed text.

The `tikz` index must use `attributeForDistinct: "search_group"`, `distinct: 2`,
and retrieve the `manual` attribute. The crawler's `initialIndexSettings` mirror
these settings, but changes to an existing index must also be applied in its
Configuration tab. New manuals and new group keys appear only after a crawl;
run the crawler after the root deployment is available, or wait for its weekly
Monday schedule. Do not crawl the staging prefix to populate production search.

Check a root URL in the crawler's URL Tester before publishing. For local
grouping and permalink checks, run `node scripts/tests/test_algolia_crawler.js`
with Cheerio available through `NODE_PATH`; an optional JSON file mapping page
paths to rendered HTML checks additional manuals without indexing anything.

## lwarp speedups

The lwarp manuals load `shared/tikz-dev-fast-lwarp.sty`, which caches parsed
argument handlers for spans and filename sanitization instead of rebuilding
them for every coloured word and link, and skips one redundant LaTeX pass. If
lwarp changes the code it relies on, it falls back to lwarp's own handler and
logs a warning. `scripts/tests/test_fast_lwarp.py` compares the HTML, references and
image lists with stock lwarp.

## Tests

```bash
python3 -m unittest discover -s scripts/tests
```

Citations are shown as author–year labels ([Tantau 2025]) rather than numbers
(`shared/citations.py`): from the `.bib` fields in the converted manuals, and
from the printed reference list in the lwarp manuals.
