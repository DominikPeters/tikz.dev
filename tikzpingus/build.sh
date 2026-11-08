#!/usr/bin/env bash
# Build the pinned TikZpingus manual, or regenerate its images/HTML.
set -euo pipefail
cd "$(dirname "$0")"
export UPSTREAM="${UPSTREAM:-$PWD/../.upstream/tikzpingus}"
step=${1:-all}
if [[ $step == all ]]; then
  python3 convert.py tex
  (
    cd build/tex
    export TEXINPUTS=".:tex//:"
    for run in 1 2; do
      echo "TikZpingus: LuaLaTeX run $run"
      if ! lualatex -halt-on-error -interaction=nonstopmode tikzpingus-html.tex > "run-$run.out" 2>&1; then
        tail -50 "run-$run.out" >&2
        exit 1
      fi
    done
  )
fi
if [[ $step == all || $step == images ]]; then
  python3 ../shared/texhtml/extract_images.py build/tex/tikzpingus-html.pdf \
    build/tex/tikzpingus-html.htmlimages build/images
fi
python3 convert.py html
