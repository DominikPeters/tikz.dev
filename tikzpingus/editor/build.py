#!/usr/bin/env python3
"""Install the Pingu editor in the manual's start page and build its SVG parts.

    python3 tikzpingus/editor/build.py [--force] [--output DIRECTORY]

Only the build needs TeX. The resulting manual runs on any static host.
The pinned package is instrumented in a disposable copy, never modified.
"""
import argparse
import copy
import ctypes.util
import hashlib
from html import unescape
import json
import os
from pathlib import Path
import re
import subprocess
import xml.etree.ElementTree as ET
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BUILD = ROOT / 'build/tikzpingus/editor'
SVG = 'http://www.w3.org/2000/svg'
ET.register_namespace('', SVG)
ET.register_namespace('xlink', 'http://www.w3.org/1999/xlink')
LAYERS = {'pingu-L-v': 0, 'pingu-L-b': 1, 'pingu-L-m': 2,
          'pingu-L-i': 3, 'pingu-L-f': 4, 'pingu-L-g': 5}
SLOTS = ['bodytype', 'lefteye', 'righteye', 'leftfoot', 'rightfoot',
         'leftwing', 'rightwing', 'bill', 'hairstyle']
PHASES = dict(zip(SLOTS, [100, 110, 111, 400, 401, 500, 501, 600, 300]))
CLOTHING_SLOTS = ['clothingbehind', 'clothingmiddle', 'clothingmain']
PHASES.update(dict(zip(CLOTHING_SLOTS, [120, 130, 550])))
REF = re.compile(r'url\(#([^\)]+)\)')


def run(command, cwd, env=None):
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'{command[0]} failed:\n{result.stdout[-5000:]}\n{result.stderr[-2000:]}')
    return result.stdout + result.stderr


def instrument(source):
    """Tag painted paths, so tags survive PGF moving them between layers."""
    start = source.index(r'\newcommand*\pingu[1][]')
    end = source.index('% <@pingu front>', start)
    body = source[start:end]
    for slot in SLOTS:
        macro = '@pingu@drawer@' + slot + '@'
        body = body.replace('\\' + macro, r'\def\editor@part{' + slot + '}\\' + macro)
    for macro in ['pingu@draw@extras@below', 'pingu@draw@extras@above',
                  'pingu@draw@wing@items']:
        body = body.replace('\\' + macro, r'\def\editor@part{extra}' + '\\' + macro)
    for suffix, slot in zip(['behind', 'middle', 'main'], CLOTHING_SLOTS):
        macro = 'pingu@draw@clothing@' + suffix
        body = body.replace('\\' + macro, r'\def\editor@part{' + slot + '}\\' + macro)
    return source[:start] + body + source[end:]


HOOK = r'''
\makeatletter
\def\editor@part{unassigned}
\def\editor@plane{pingu-L-m}
\let\editor@path\pgf@sys@svg@possiblyclippedpath
\def\pgf@sys@svg@possiblyclippedpath#1{\editor@path{#1 data-part="\editor@part" data-plane="\editor@plane"}}
\let\editor@shading\pgfsys@shadinginsidepgfpicture
\def\pgfsys@shadinginsidepgfpicture#1{%
  \pgfsysprotocol@literal{<g data-part="\editor@part" data-plane="\editor@plane">}%
  \editor@shading{#1}\pgfsysprotocol@literal{</g>}}
\let\editor@hbox\pgfsys@hbox
\def\pgfsys@hbox#1{\pgfsys@invoke{<g data-part="\editor@part" data-plane="\editor@plane">}%
  \editor@hbox{#1}\pgfsys@invoke{</g>}}
\let\editor@hboxsynced\pgfsys@hboxsynced
\def\pgfsys@hboxsynced#1{\pgfsys@invoke{<g data-part="\editor@part" data-plane="\editor@plane">}%
  \editor@hboxsynced{#1}\pgfsys@invoke{</g>}}
\let\editor@layer\pgfonlayer
\def\pgfonlayer#1{\editor@layer{#1}\edef\editor@plane{#1}}
\makeatother
'''


def cases(catalog):
    result = []
    for body in catalog['bodies']:
        common = 'body type=' + body['tex']
        result.append(dict(body=body['id'], id='base', tex=common, slots=SLOTS))
        for family, key, slots in [('eyes', 'eyes', ['lefteye', 'righteye']),
                                   ('wings', 'wings', ['leftwing', 'rightwing']),
                                   ('bills', 'bill', ['bill']),
                                   ('feet', 'feet', ['leftfoot', 'rightfoot'])]:
            for choice in catalog[family]:
                if choice['id'] == 'normal':
                    continue
                result.append(dict(body=body['id'], id=family + '-' + choice['id'],
                                   tex=common + ',' + key + '=' + choice['tex'], slots=slots))
        for family in ['headwear', 'eyewear', 'neckwear', 'belly', 'clothing']:
            for choice in catalog[family]:
                if choice['id'] == 'none':
                    continue
                result.append(dict(body=body['id'], id=family + '-' + choice['id'],
                                   tex=common + ',' + choice['tex'],
                                   slots=CLOTHING_SLOTS if family == 'clothing' else ['extra']))
        for choice in catalog['items']:
            if choice['id'] == 'none':
                continue
            for side in ['left', 'right']:
                result.append(dict(body=body['id'], id='item-' + side + '-' + choice['id'],
                                   tex=common + ',' + side + ' wing=grab,' + choice['tex'] + ' ' + side,
                                   slots=['extra']))
    return result


def phases(source):
    """Order accessories as the package does, rather than by UI selection."""
    result = dict(PHASES)
    for suffix, offset in [('eb', 200), ('ea', 700)]:
        start = source.index('\\def\\pingu@draw@extras@' + ('below' if suffix == 'eb' else 'above') + '{')
        end = source.index('\n}', start)
        names = re.findall(r'\\pingu@xif@' + suffix + r'\{([^}]+)\}', source[start:end])
        for n, name in enumerate(names):
            result[name] = offset + n
    return result


def references(element):
    result = set()
    for node in element.iter():
        for attr, value in node.attrib.items():
            result.update(REF.findall(value))
            if attr.rsplit('}', 1)[-1] == 'href' and value.startswith('#'):
                result.add(value[1:])
    return result


def prune(element, slot, plane):
    if element.get('data-part') == slot and element.get('data-plane') == plane:
        return copy.deepcopy(element)
    if element.tag.rsplit('}', 1)[-1] in {'defs', 'clipPath'}:
        return None
    clone = ET.Element(element.tag, element.attrib)
    for child in element:
        kept = prune(child, slot, plane)
        if kept is not None:
            clone.append(kept)
    return clone if len(clone) else None


def color_roles(element, slot):
    for node in element.iter():
        for attr in ['fill', 'stroke']:
            color = node.get(attr, '').lower()
            role = None
            if slot in {'bodytype', 'hairstyle', 'leftwing', 'rightwing'} and color == '#030e1d':
                role = 'body'
            elif slot == 'bodytype' and color == '#f8f8f8':
                role = 'belly'
            elif slot in {'lefteye', 'righteye'} and color == '#171313':
                role = 'eyes'
            elif slot == 'bill' and color == '#fcbb15':
                role = 'bill'
            elif slot in {'leftfoot', 'rightfoot'} and color == '#fcbb15':
                role = 'feet'
            if role:
                node.set('data-' + attr, role)


def extract(root, slot, plane, prefix):
    parents = {child: parent for parent in root.iter() for child in parent}
    ids = {e.get('id'): e for e in root.iter() if e.get('id')}
    group = prune(root, slot, plane)
    if group is None:
        return None
    group.tag = '{' + SVG + '}g'
    group.attrib.clear()
    # Shadings contain inline definitions; hoist them with the other resources.
    # PGF can repeat the same gradient ID, so keep one definition per part.
    resources = {'clipPath', 'radialGradient', 'linearGradient', 'pattern'}
    for parent in list(group.iter()):
        for child in list(parent):
            if child.tag.rsplit('}', 1)[-1] in resources:
                parent.remove(child)
    needed, done = references(group), set()
    defs = ET.Element('{' + SVG + '}defs')
    while needed - done:
        name = sorted(needed - done)[0]
        if name not in ids:
            raise ValueError('Missing SVG definition: ' + name)
        original = ids[name]
        clone = copy.deepcopy(original)
        # dvisvgm places clip definitions inline; retain their inherited rule.
        for attr in ['fill-rule', 'clip-rule']:
            ancestor = original
            while ancestor is not None and attr not in clone.attrib:
                if attr in ancestor.attrib:
                    clone.set(attr, ancestor.get(attr))
                ancestor = parents.get(ancestor)
        defs.append(clone)
        done.add(name)
        needed |= references(clone)
    if len(defs):
        group.insert(0, defs)
    for node in group.iter():
        for attr, value in list(node.attrib.items()):
            if attr == 'id':
                node.set(attr, prefix + value)
            else:
                value = re.sub(r'url\(#([^\)]+)\)', lambda m: 'url(#' + prefix + m[1] + ')', value)
                if value.startswith('#') and value[1:] in ids:
                    value = '#' + prefix + value[1:]
                node.set(attr, value)
        node.attrib.pop('data-part', None)
        node.attrib.pop('data-plane', None)
    color_roles(group, slot)
    return group


def generate(source, catalog, work, tools):
    modified = instrument(source)
    all_cases = cases(catalog)
    pictures = '\n'.join(r'\begin{tikzpicture}\path[use as bounding box] (-2,-2.6) rectangle (4,4);'
                         r'\begin{pgfinterruptboundingbox}\pingu[' + c['tex'] + ']'
                         r'\end{pgfinterruptboundingbox}\end{tikzpicture}' for c in all_cases)
    tex = (r'\documentclass[multi=tikzpicture,border=0pt]{standalone}' '\n'
           r'\def\pgfsysdriver{pgfsys-dvisvgm.def}' '\n'
           r'\usepackage[noglows]{tikzpingus}' + HOOK + '\n' +
           r'\begin{document}' + pictures + r'\end{document}')
    libgs = os.environ.get('LIBGS') or ctypes.util.find_library('gs')
    if not libgs and Path('/opt/homebrew/lib/libgs.dylib').exists():
        libgs = '/opt/homebrew/lib/libgs.dylib'
    native = BUILD / 'native' / digest((modified + tex + tools + str(libgs)).encode())
    native.mkdir(parents=True, exist_ok=True)
    if not (native / 'complete').exists():
        (native / 'tikzpingus.sty').write_text(modified)
        (native / 'parts.tex').write_text(tex)
        print(f'Pingu editor: compiling {len(all_cases)} native drawings', flush=True)
        run(['latex', '-halt-on-error', '-interaction=nonstopmode', 'parts.tex'], native,
            dict(os.environ, TEXINPUTS='.:'))
        command = ['dvisvgm', '--no-fonts', '--exact', '--page=1-', '--output=page-%p.svg']
        if libgs:
            command.append('--libgs=' + libgs)
        run(command + ['parts.dvi'], native)
        (native / 'complete').write_text('1\n')
    order = phases(source)
    for body in catalog['bodies']:
        pack = ET.Element('{' + SVG + '}svg', {'viewBox': '-72 -72 170.08 187.09'})
        for page, case in enumerate(all_cases, 1):
            if case['body'] != body['id']:
                continue
            root = ET.parse(native / ('page-' + str(page).zfill(len(str(len(all_cases)))) + '.svg')).getroot()
            if case['id'] == 'base':
                thumbnail = copy.deepcopy(root)
                thumbnail.set('viewBox', '-26 1 80 95')
                thumbnail.set('width', '80'); thumbnail.set('height', '95')
                for node in thumbnail.iter():
                    node.attrib.pop('data-part', None); node.attrib.pop('data-plane', None)
                (work / ('thumb-' + body['id'] + '.svg')).write_bytes(ET.tostring(thumbnail))
            for slot in case['slots']:
                part_id = case['id'] + '-' + slot
                part = ET.SubElement(pack, '{' + SVG + '}g', {'id': part_id})
                for plane, layer in LAYERS.items():
                    group = extract(root, slot, plane, part_id + '-' + str(layer) + '-')
                    if group is None:
                        continue
                    phase = order.get(slot, 800)
                    if slot == 'extra':
                        choice_id = case['id'].split('-', 1)[1]
                        phase = order.get({'sunglasses': 'glasses'}.get(choice_id, choice_id),
                                          800 + (case['id'].startswith('item-right-')))
                    group.set('data-z', str(layer * 10000 + phase))
                    part.append(group)
        data = ET.tostring(pack, encoding='utf-8', xml_declaration=True)
        (work / (body['id'] + '.svg')).write_bytes(data)
    (work / 'complete').write_text('1\n')


def digest(data):
    return hashlib.sha256(data).hexdigest()[:12]


def documentation(site, catalog):
    """Use the manual's own key index, including its real alias anchors."""
    index = (site / 'key-index.html').read_text()
    all_keys = {unescape(name): unescape(href) for href, name in
                re.findall(r'<a href="([^"]+)"><kbd>([^<]+)</kbd></a>', index)}
    wanted = {'\\pingu', 'body type', 'eyes', 'left wing', 'right wing', 'bill', 'feet',
              'hairstyle', 'hairstyle none', 'body', 'wings color'}
    wanted.update(c['tex'] for c in catalog['colors'])
    for family, key in [('bodies', 'body type'), ('eyes', 'eyes'), ('wings', 'left wing'),
                        ('wings', 'right wing'), ('bills', 'bill'), ('feet', 'feet')]:
        wanted.update(key + ' ' + choice['tex'] for choice in catalog[family])
    for family in ['headwear', 'eyewear', 'neckwear', 'belly', 'clothing']:
        wanted.update(choice['tex'] for choice in catalog[family] if choice['tex'])
    wanted.update(choice['tex'] + ' ' + side for choice in catalog['items']
                  if choice['tex'] for side in ['left', 'right'])
    keys = {key: all_keys[key] for key in sorted(wanted) if key in all_keys}
    keys['\\definecolor'] = 'usage-colors'
    groups = {'body': keys['body type'], 'feet': keys['feet'], 'hair': keys['hairstyle'],
              'eyes': keys['eyes'], 'bill': keys['bill'], 'leftWing': keys['left wing'],
              'rightWing': keys['right wing'], 'headwear': 'overview', 'eyewear': 'ref-glasses',
              'neckwear': 'ref-extras', 'belly': 'ref-extras', 'clothing': 'clothes', 'colors': 'usage-colors'}
    # Fail the build instead of shipping a documentation button to a missing anchor.
    anchors = {}
    for href in set(keys.values()) | set(groups.values()):
        target = urlsplit(href)
        page = site / (target.path + '.html')
        if page not in anchors:
            anchors[page] = {unescape(a) for a in re.findall(r'\bid="([^"]+)"', page.read_text())}
        if target.fragment and unquote(target.fragment) not in anchors[page]:
            raise ValueError('Missing editor documentation target: ' + href)
    return {'keys': keys, 'groups': groups}


def replace_section(html, start, end, content):
    if html.count(start) != 1 or html.count(end) != 1:
        raise ValueError('Missing or duplicate editor mount in the manual start page')
    before, rest = html.split(start, 1)
    _, after = rest.split(end, 1)
    return before + start + '\n' + content + '\n' + end + after


def install(home, fragment, css_file, app_file):
    html = home.read_text()
    html = replace_section(html, '<!-- pingu-editor -->', '<!-- /pingu-editor -->', fragment)
    start, end = '<!-- pingu-editor-assets -->', '<!-- /pingu-editor-assets -->'
    assets = (f'<link rel="stylesheet" href="editor/{css_file}">\n'
              f'<script type="module" src="editor/{app_file}"></script>')
    if start not in html:
        html = html.replace('</head>', start + end + '\n</head>', 1)
    html = replace_section(html, start, end, assets)
    home.write_text(html)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/tikzpingus/site/editor')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    output = args.output.resolve()
    home = output.parent / 'index.html'
    if not home.is_file() or '<!-- pingu-editor -->' not in home.read_text():
        raise SystemExit('Build the manual HTML first: python3 tikzpingus/convert.py html')
    upstream = Path(os.environ.get('UPSTREAM', ROOT / '.upstream/tikzpingus'))
    source = (upstream / 'tex/tikzpingus.sty').read_text()
    catalog = json.loads((HERE / 'catalog.json').read_text())
    catalog['documentation'] = documentation(home.parent, catalog)
    tools = '\n'.join(run([tool, '--version'], ROOT) for tool in ['latex', 'dvisvgm'])
    key = digest((source + tools + (HERE / 'catalog.json').read_text() + Path(__file__).read_text()).encode())
    work = BUILD / 'cache' / key
    if args.force or not (work / 'complete').exists():
        work.mkdir(parents=True, exist_ok=True)
        generate(source, catalog, work, tools)
    output.mkdir(parents=True, exist_ok=True)
    assets = output / 'assets'
    assets.mkdir(exist_ok=True)
    catalog['packs'] = {}
    for body in catalog['bodies']:
        data = (work / (body['id'] + '.svg')).read_bytes()
        name = body['id'] + '.' + digest(data) + '.svg'
        (assets / name).write_bytes(data)
        catalog['packs'][body['id']] = 'assets/' + name
        thumb = (work / ('thumb-' + body['id'] + '.svg')).read_bytes()
        thumb_name = 'thumb-' + body['id'] + '.' + digest(thumb) + '.svg'
        (assets / thumb_name).write_bytes(thumb)
        body['thumbnail'] = 'assets/' + thumb_name
    payload = json.dumps(catalog, separators=(',', ':')).encode()
    catalog_file = 'catalog.' + digest(payload) + '.json'
    (output / catalog_file).write_bytes(payload)
    core = (HERE / 'core.mjs').read_bytes()
    core_file = 'core.' + digest(core) + '.mjs'
    (output / core_file).write_bytes(core)
    app = (HERE / 'app.js').read_text().replace('__CORE__', core_file).replace('__CATALOG__', catalog_file).encode()
    app_file = 'app.' + digest(app) + '.js'
    (output / app_file).write_bytes(app)
    css = (HERE / 'style.css').read_bytes()
    css_file = 'style.' + digest(css) + '.css'
    (output / css_file).write_bytes(css)
    install(home, (HERE / 'editor.html').read_text(), css_file, app_file)
    (output / 'LICENSE-tikzpingus.txt').write_bytes((upstream / 'LICENSE').read_bytes())
    (output / '.htaccess').write_text('<IfModule mod_mime.c>\nAddType text/javascript .mjs\n</IfModule>\n'
                                    '<IfModule mod_deflate.c>\nAddOutputFilterByType DEFLATE text/html text/css text/javascript application/javascript application/json image/svg+xml\n</IfModule>\n')
    # Remove obsolete content-hashed files, never anything outside this editor.
    keep = {'assets', catalog_file, core_file, app_file, css_file, '.htaccess', 'LICENSE-tikzpingus.txt'}
    for path in output.iterdir():
        if path.is_file() and path.name not in keep:
            path.unlink()
    asset_names = {Path(p).name for p in catalog['packs'].values()} | {Path(b['thumbnail']).name for b in catalog['bodies']}
    for path in assets.iterdir():
        if path.is_file() and path.name not in asset_names:
            path.unlink()
    print(f'Pingu editor: installed in {home.relative_to(ROOT) if home.is_relative_to(ROOT) else home}', flush=True)


if __name__ == '__main__':
    main()
