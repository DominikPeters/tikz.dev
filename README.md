# tikz.dev

Sources of [tikz.dev](https://tikz.dev) which features HTML versions of the manuals of
PGF/TikZ and related packages:

| Manual | On tikz.dev | Upstream |
|---|---|---|
| PGF/TikZ | [tikz.dev](https://tikz.dev/) | [pgf-tikz/pgf](https://github.com/pgf-tikz/pgf) |
| PGFplots | [/pgfplots/](https://tikz.dev/pgfplots/) | [pgf-tikz/pgfplots](https://github.com/pgf-tikz/pgfplots) |
| tcolorbox | [/tcolorbox/](https://tikz.dev/tcolorbox/) | [T-F-S/tcolorbox](https://github.com/T-F-S/tcolorbox) |
| tikz-cd | [/tikz-cd/](https://tikz.dev/tikz-cd/) | [astoff/tikz-cd](https://github.com/astoff/tikz-cd) |
| pgf-pie | [/pgf-pie/](https://tikz.dev/pgf-pie/) | [pgf-tikz/pgf-pie](https://github.com/pgf-tikz/pgf-pie) |
| TikZ-Feynman | [/tikz-feynman/](https://tikz.dev/tikz-feynman/) | [JP-Ellis/tikz-feynman](https://github.com/JP-Ellis/tikz-feynman) |
| TikZpingus | [/tikzpingus/](https://tikz.dev/tikzpingus/) | [EagleoutIce/tikzpingus](https://github.com/EagleoutIce/tikzpingus) |
| wheelchart | [/wheelchart/](https://tikz.dev/wheelchart/) | [CTAN](https://ctan.org/pkg/wheelchart) |
| pgfgantt | [/pgfgantt/](https://tikz.dev/pgfgantt/) | [skafdasschaf/latex-pgfgantt](https://github.com/skafdasschaf/latex-pgfgantt) |
| tkz-euclide | [/tkz-euclide/](https://tikz.dev/tkz-euclide/) | [CTAN](https://ctan.org/pkg/tkz-euclide) |
| chemfig | [/chemfig/](https://tikz.dev/chemfig/) | [CTAN](https://ctan.org/pkg/chemfig) |
| forest | [/forest/](https://tikz.dev/forest/) | [sasozivanovic/forest](https://github.com/sasozivanovic/forest) |
| nicematrix | [/nicematrix/](https://tikz.dev/nicematrix/) | [fpantigny/nicematrix](https://github.com/fpantigny/nicematrix) |

Feedback, suggestions and bug reports are welcome as
[issues](https://github.com/DominikPeters/tikz.dev/issues).

## How it works

The HTML manuals are built from their sources (taken from GitHub or CTAN) using one of two methods:

* **[lwarp](https://ctan.org/pkg/lwarp)**: a LaTeX package that converts a LaTeX document to HTML. 
It is used for PGF/TikZ, PGFplots, tcolorbox, and wheelchart. The resulting HTML files are then
postprocessed using a Python script to add the header, menu, and other features of tikz.dev.
A self-contained version of this pipeline is available at https://github.com/DominikPeters/tikz.dev-style/.
* **Python converters**: Other manuals are converted to HTML using custom Python converters that
parse the LaTeX source and generate HTML. There were written by Claude (Opus 5.5) and are used for 
tikz-cd, TikZ-Feynman, pgfgantt, tkz-euclide, chemfig, forest, nicematrix, and TikZpingus.

The builds are run in a GitHub Action. We also use actions to automatically and regularly check for changes
to the upstream manuals. When a change causes the build to fail, the action opens an issue in this repository.
Each package has a file `upstream.lock` which specifies the upstream commit or CTAN version that was last successfully built.

## Building a manual locally

```bash
scripts/fetch.sh pgf      # upstream checkout at the pinned commit
scripts/build.sh pgf      # result in build/pgf/site
scripts/serve.py          # http://127.0.0.1:8765/, with every manual built so far
```

This needs a recent TeX Live with LuaLaTeX and lwarp, Python 3 and the image
tools listed in [.github/workflows/build-package.yml](.github/workflows/build-package.yml).
The full PGF and pgfplots manuals take 30-50 minutes; the smaller manuals are fast.

## Repository layout

```
<package>/     one folder per manual: upstream.lock, patches/, build.sh,
               postprocessing.py, HTML adaptations; README.md with notes
shared/        style.css, pgfmanual.js, the header menu and the build tools
               shared by all manuals (image conversion, caches, checks)
scripts/       fetch.sh, prepare.py, build.sh, serve.py, deploy.sh; tests/ for
               the build tools (python3 -m unittest discover -s scripts/tests)
docs/          how the build works in detail
```

More detail:

* [docs/building.md](docs/building.md): building, patches, the shared frontend
* [docs/caching.md](docs/caching.md): drawing reuse, image conversion and formats
* [docs/converters.md](docs/converters.md): manuals converted without lwarp (tcolorbox, tkz-euclide, chemfig, forest, nicematrix)
* [docs/automation.md](docs/automation.md): GitHub Actions, upstream updates, deployment
* [docs/migration.md](docs/migration.md): moving from the old fork repositories

## License

The tikz.dev tooling (scripts, workflows, `shared/`, build and postprocessing
scripts, the tcolorbox converter) is under the [MIT license](LICENSE). The
manuals belong to their authors and keep their licenses, which also apply to
the patches and adaptations derived from them and to the generated pages.
[REUSE.toml](REUSE.toml) lists which files fall under which license.
