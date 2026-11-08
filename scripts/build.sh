#!/usr/bin/env bash
# Build one manual into build/<package>/site (upstream must be fetched first).
#
#   scripts/fetch.sh pgf && scripts/build.sh pgf
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
pkg=${1:?usage: scripts/build.sh <package>}
docdir=$(sed -n 's/^docdir=//p' "$root/$pkg/upstream.lock")
out="$root/build/$pkg/site"
# Outside the disposable prepared source trees; also restored by CI.
export TIKZ_IMAGE_CACHE="${TIKZ_IMAGE_CACHE:-$root/build/image-cache}"

native_key=""
if [[ ${TIKZ_COMPILED_CACHE_ENABLED:-1} != 0 ]]; then
  native_key=$(python3 "$root/scripts/native_cache.py" key "$pkg") || native_key=""
fi
if [[ -n $native_key ]] && python3 "$root/scripts/native_cache.py" restore "$pkg" "$native_key"; then
  python3 "$root/scripts/native_cache.py" html "$pkg"
  if [[ -f $root/$pkg/convert.py ]]; then
    site="$root/$pkg/build/site/$pkg"
    python3 "$root/shared/check_manual_site.py" "$site"
  else
    site="$root/build/$pkg/src/$docdir/processed"
  fi
else
  case $pkg in
    tcolorbox|tkz-euclide|chemfig|forest|nicematrix|tikzpingus)
      # converted without lwarp (docs/converters.md), reads the upstream checkout directly
      UPSTREAM="$root/.upstream/$pkg" "$root/$pkg/build.sh"
      site="$root/$pkg/build/site/$pkg"
      python3 "$root/shared/check_manual_site.py" "$site"
      ;;
    *)
      # lwarp-based manuals: build in the prepared upstream tree
      python3 "$root/scripts/prepare.py" "$pkg"
      # Keep the HTML helpers in the documentation directory ahead of upstream
      # files with the same names, then use the package code matching the docs.
      tex="$root/build/$pkg/src/tex"
      (cd "$root/build/$pkg/src/$docdir" &&
        TEXINPUTS=".:$tex//:${TEXINPUTS:-}" LUAINPUTS=".:$tex//:${LUAINPUTS:-}" ./build.sh)
      # build.sh carries on after LaTeX errors; don't publish a half-built site
      for log in "$root/build/$pkg/src/$docdir"/*_html.log; do
        if grep -q "Fatal error occurred" "$log" || ! grep -q "^Output written on" "$log"; then
          grep -m1 -A3 "^! " "$log" || true
          echo "$pkg: LaTeX failed, see ${log#$root/}" >&2
          exit 1
        fi
      done
      site="$root/build/$pkg/src/$docdir/processed"
      ;;
  esac
fi

if [[ ! -f $site/index.html ]]; then
  echo "$pkg: no index.html in ${site#$root/}, not a complete site" >&2
  exit 1
fi
if [[ -n $native_key ]]; then
  python3 "$root/scripts/native_cache.py" save "$pkg" "$native_key" || echo "$pkg: compiled cache could not be saved" >&2
fi
rm -rf "$out"
mkdir -p "$(dirname "$out")"
cp -R "$site" "$out"
echo "$pkg: site in ${out#$root/} ($(find "$out" -type f | wc -l | tr -d ' ') files)"
