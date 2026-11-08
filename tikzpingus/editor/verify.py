#!/usr/bin/env python3
"""Compare browser-exported fixtures with independently compiled TikZpingus.

Input: JSON array of {name, svg, tex} objects captured from the built editor.
Outputs native TeX/SVG, raster pairs, and an inspectable report under build/.
"""
import argparse
import ctypes.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]


def run(command, cwd, env=None):
    p = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError(p.stdout[-3000:] + p.stderr[-1000:])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fixtures', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/tikzpingus/editor/verification')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    fixtures = json.loads(args.fixtures.read_text())
    # Reference uses the unmodified pinned package, not the instrumented copy.
    shutil.copyfile(ROOT / '.upstream/tikzpingus/tex/tikzpingus.sty', output / 'tikzpingus.sty')
    pictures = '\n'.join(r'\begin{tikzpicture}\path[use as bounding box] (-2,-2.6) rectangle (4,4);'
                         r'\begin{pgfinterruptboundingbox}' + f['tex'] +
                         r'\end{pgfinterruptboundingbox}\end{tikzpicture}' for f in fixtures)
    tex = (r'\documentclass[multi=tikzpicture,border=0pt]{standalone}' '\n'
           r'\def\pgfsysdriver{pgfsys-dvisvgm.def}' '\n'
           r'\usepackage[noglows]{tikzpingus}\begin{document}' + pictures + r'\end{document}')
    (output / 'reference.tex').write_text(tex)
    run(['latex', '-halt-on-error', '-interaction=nonstopmode', 'reference.tex'], output,
        dict(os.environ, TEXINPUTS='.:'))
    command = ['dvisvgm', '--no-fonts', '--exact', '--page=1-', '--output=native-%p.svg']
    libgs = ctypes.util.find_library('gs')
    if not libgs and Path('/opt/homebrew/lib/libgs.dylib').exists():
        libgs = '/opt/homebrew/lib/libgs.dylib'
    if libgs:
        command.append('--libgs=' + libgs)
    run(command + ['reference.dvi'], output)
    report = []
    digits = len(str(len(fixtures)))
    for i, fixture in enumerate(fixtures, 1):
        name = str(i).zfill(digits)
        native = output / ('native-' + name + '.svg')
        root = ET.fromstring(fixture['svg'])
        for attr in ['viewBox', 'width', 'height']:
            root.set(attr, ET.parse(native).getroot().get(attr))
        composed = output / ('composed-' + name + '.svg')
        composed.write_bytes(ET.tostring(root))
        arrays = []
        for path in [native, composed]:
            run(['rsvg-convert', '-w', '680', '-h', '748', '-b', 'white',
                 '-o', str(path.with_suffix('.png')), str(path)], output)
            arrays.append(np.array(Image.open(path.with_suffix('.png')).convert('RGB')).astype(int))
        delta = np.abs(arrays[0] - arrays[1])
        record = dict(name=fixture['name'], page=i, mean=float(delta.mean()), max=int(delta.max()),
                      changed_pixels=int(np.any(delta, axis=2).sum()))
        report.append(record)
    (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    failures = [r for r in report if r['mean'] > .025]
    print(f'{len(report)} native SVG comparisons; {len(failures)} differences above 0.025 mean pixel error')
    for r in failures:
        print(json.dumps(r))
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
