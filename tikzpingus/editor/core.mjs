// Small, dependency-free state, SVG composition, and TeX export helpers.
export const NS = 'http://www.w3.org/2000/svg';
const FAMILIES = {body:'bodies', eyes:'eyes', leftWing:'wings', rightWing:'wings',
  bill:'bills', feet:'feet', headwear:'headwear', eyewear:'eyewear',
  neckwear:'neckwear', belly:'belly', clothing:'clothing', leftItem:'items', rightItem:'items'};

export function defaults(catalog) {
  return {body:'normal', eyes:'shiny', leftWing:'wave', rightWing:'normal', bill:'normal',
    feet:'normal', headwear:'none', eyewear:'none', neckwear:'none', belly:'none', clothing:'none',
    leftItem:'none', rightItem:'none', hair:true,
    colors:Object.fromEntries(catalog.colors.map(c => [c.id, c.default]))};
}

export function normalize(input, catalog) {
  const state = defaults(catalog);
  if (!input || typeof input !== 'object') return state;
  for (const [key, family] of Object.entries(FAMILIES)) {
    if (catalog[family].some(c => c.id === input[key])) state[key] = input[key];
  }
  if (typeof input.hair === 'boolean') state.hair = input.hair;
  for (const c of catalog.colors) {
    const value = input.colors?.[c.id];
    if (typeof value === 'string' && /^#[\da-f]{6}$/i.test(value)) state.colors[c.id] = value.toLowerCase();
  }
  for (const side of ['left', 'right']) if (state[side+'Item'] !== 'none') state[side+'Wing'] = 'grab';
  return state;
}

export function update(state, key, value, catalog) {
  const next = {...state, colors:{...state.colors}};
  if (key.startsWith('color:')) next.colors[key.slice(6)] = value;
  else next[key] = value;
  for (const side of ['left', 'right']) {
    if (key === side+'Wing' && value !== 'grab') next[side+'Item'] = 'none';
  }
  return normalize(next, catalog);
}

// These option positions and defaults are part of the v2 link format. Append
// new options; never reorder them or derive their codes from catalog order.
const SHARE_FIELDS = [
  ['b','body','normal',['normal','chubby','legacy']],
  ['e','eyes','shiny',['normal','shiny','wink','sad','angry','hearts','shock','critical','vertical','devil','none']],
  ['l','leftWing','wave',['normal','wave','raise','grab','shock','hug','none']],
  ['r','rightWing','normal',['normal','wave','raise','grab','shock','hug','none']],
  ['k','bill','normal',['normal','flat','open','angry']],
  ['f','feet','normal',['normal','sit','simple','back','chubby','none']],
  ['h','headwear','none',['none','hat','strawhat','graduate','crown','princesscrown','constructionhelmet','santahat','woolhat','pumpkinhat','bunnyears','devilhorns','headphone']],
  ['g','eyewear','none',['none','glasses','glassesround','sunglasses','monocleleft','eyepatchleft']],
  ['n','neckwear','none',['none','tie','bowtie','scarf']],
  ['a','belly','none',['none','cup','heart']],
  ['i','leftItem','none',['none','flower','lollipop','snowball','staff','microphone','guitar','laptop']],
  ['j','rightItem','none',['none','flower','lollipop','snowball','staff','microphone','guitar','laptop']],
  ['c','clothing','none',['none','shirt','sweater','cape']]
];
const SHARE_COLORS = [['B','body'],['W','belly'],['E','eyes'],['K','bill'],['F','feet']];

// Palette positions are also stable share codes. Labels may change; existing
// colors/positions must stay fixed. The UI uses the same palette definitions.
export const PALETTES = [
  ['Classic',['#030e1d','#f8f8f8','#171313','#fcbb15','#fcbb15']],
  ['Forest',['#355a45','#f4efda','#182d26','#dca34e','#dca34e']],
  ['Berry',['#75405b','#fff1e8','#332233','#efa56e','#efa56e']],
  ['Ocean',['#285b77','#e5f4f3','#153141','#efb340','#efb340']],
  ['Lavender',['#77648b','#f6effb','#34283d','#f5c678','#f5c678']],
  ['Rose',['#a04a5f','#fff4f1','#3a1d26','#f2a65a','#f2a65a']]
];

export function isShareHash(hash) {
  return typeof hash === 'string' && (hash.startsWith('#v1=') || hash.startsWith('#v2='));
}

export function encode(state) {
  const tokens = [];
  for (const [code,key,base,options] of SHARE_FIELDS) {
    const value = state[key] ?? base;
    if (value === base) continue;
    // A held item already implies this pose when decoded.
    if (key.endsWith('Wing') && value === 'grab' && (state[key.replace('Wing','Item')] ?? 'none') !== 'none') continue;
    const index = options.indexOf(value);
    tokens.push(code + (index < 0 ? '~'+encodeURIComponent(value).replaceAll('.','%2E') : index.toString(36)));
  }
  if (state.hair === false) tokens.push('t0');
  // Pick the palette that needs the fewest color overrides. Custom colors use
  // three hex digits when possible, otherwise six, without the redundant '#'.
  const colors = PALETTES.map(([,values],index) => {
    const parts = index ? ['p'+index.toString(36)] : [];
    for (const [i,[code,key]] of SHARE_COLORS.entries()) {
      const value = (state.colors?.[key] ?? PALETTES[0][1][i]).toLowerCase();
      if (value === values[i]) continue;
      const hex = value.slice(1);
      parts.push(code + (/^(.)\1(.)\2(.)\3$/.test(hex) ? hex[0]+hex[2]+hex[4] : hex));
    }
    return parts.join('.');
  }).reduce((best,value) => value.length < best.length ? value : best);
  if (colors) tokens.push(colors);
  // Even the default pingu needs an explicit hash, to override saved settings.
  return '#v2=' + tokens.join('.');
}

export function decode(hash, catalog) {
  if (!isShareHash(hash) || hash.length > 4096) throw new Error('Invalid Pingu link');
  if (hash.startsWith('#v1=')) {
    return normalize(JSON.parse(atob(hash.slice(4).replaceAll('-','+').replaceAll('_','/'))), catalog);
  }
  const input = Object.fromEntries(SHARE_FIELDS.map(([,key,base]) => [key,base]));
  input.hair = true;
  const overrides = {}, seen = new Set();
  let palette = 0;
  for (const token of hash.slice(4) ? hash.slice(4).split('.') : []) {
    const code = token[0], value = token.slice(1);
    if (!value || seen.has(code)) throw new Error('Invalid Pingu link');
    seen.add(code);
    const field = SHARE_FIELDS.find(([id]) => id === code);
    const color = SHARE_COLORS.find(([id]) => id === code);
    if (field) {
      const [,key,,options] = field;
      const option = value.startsWith('~') ? decodeURIComponent(value.slice(1)) :
        /^[0-9a-z]+$/.test(value) ? options[parseInt(value,36)] : undefined;
      if (!catalog[FAMILIES[key]].some(c => c.id === option)) throw new Error('Invalid Pingu option');
      input[key] = option;
    } else if (color && /^(?:[\da-f]{3}|[\da-f]{6})$/i.test(value)) {
      overrides[color[1]] = '#'+(value.length === 3 ? [...value].map(c => c+c).join('') : value).toLowerCase();
    } else if (code === 't' && /^[01]$/.test(value)) input.hair = value === '1';
    else if (code === 'p' && /^[0-9a-z]+$/.test(value) && PALETTES[parseInt(value,36)]) palette = parseInt(value,36);
    else throw new Error('Invalid Pingu link');
  }
  input.colors = {...Object.fromEntries(SHARE_COLORS.map(([,key],i) => [key,PALETTES[palette][1][i]])),...overrides};
  return normalize(input,catalog);
}

export function tex(state, catalog, complete = false) {
  const keys = [], colors = [];
  const option = (family, id) => catalog[family].find(c => c.id === id)?.tex;
  for (const [key, family, name, base] of [
    ['body','bodies','body type','normal'], ['eyes','eyes','eyes','normal'],
    ['leftWing','wings','left wing','normal'], ['rightWing','wings','right wing','normal'],
    ['bill','bills','bill','normal'], ['feet','feet','feet','normal']]) {
    if (state[key] !== base) keys.push(name + '=' + option(family,state[key]));
  }
  if (!state.hair) keys.push('hairstyle=none');
  for (const family of ['headwear','eyewear','neckwear','belly','clothing']) {
    const value = option(family,state[family]);
    if (value) keys.push(value);
  }
  for (const side of ['left','right']) {
    const value = option('items',state[side+'Item']);
    if (value) keys.push(value+' '+side);
  }
  for (const c of catalog.colors) if (state.colors[c.id] !== c.default) {
    const name = 'pingu' + c.id[0].toUpperCase() + c.id.slice(1);
    colors.push('\\definecolor{'+name+'}{HTML}{'+state.colors[c.id].slice(1).toUpperCase()+'}');
    keys.push(c.tex+'='+name);
    if (c.id === 'body') keys.push('wings color='+name);
  }
  // Keep the first option on the opening line: the package adds a leading
  // space itself, so a newline there would leave an extra space in the key.
  const pingu = keys.length ? '\\pingu['+keys.join(',\n  ')+'\n]' : '\\pingu';
  const snippet = [...colors, pingu].join('\n');
  if (!complete) return snippet;
  return '\\documentclass[tikz,border=5pt]{standalone}\n\\usepackage{tikzpingus}\n\n'+
    '\\begin{document}\n\\begin{tikzpicture}\n'+snippet+'\n\\end{tikzpicture}\n\\end{document}\n';
}

function selectedParts(state, catalog) {
  const result = ['base-bodytype'];
  const core = (family, choice, slots) => {
    for (const slot of slots) result.push((choice === 'normal' ? 'base' : family+'-'+choice)+'-'+slot);
  };
  core('eyes',state.eyes,['lefteye','righteye']);
  core('wings',state.leftWing,['leftwing']); core('wings',state.rightWing,['rightwing']);
  core('bills',state.bill,['bill']); core('feet',state.feet,['leftfoot','rightfoot']);
  const hat = catalog.headwear.find(c => c.id === state.headwear);
  if (state.hair && !hat?.hideHair) result.push('base-hairstyle');
  for (const family of ['headwear','eyewear','neckwear','belly']) {
    if (state[family] !== 'none') result.push(family+'-'+state[family]+'-extra');
  }
  if (state.clothing !== 'none') {
    for (const slot of ['clothingbehind','clothingmiddle','clothingmain']) result.push('clothing-'+state.clothing+'-'+slot);
  }
  for (const side of ['left','right']) if (state[side+'Item'] !== 'none') {
    result.push('item-'+side+'-'+state[side+'Item']+'-extra');
  }
  return result;
}

export function parsePack(text) {
  const xml = new DOMParser().parseFromString(text,'image/svg+xml');
  if (xml.querySelector('parsererror')) throw new Error('Could not read the drawing library.');
  return new Map([...xml.documentElement.children].map(e => [e.id, e]));
}

export function compose(pack, state, catalog, prefix = 'pingu-') {
  const svg = document.createElementNS(NS,'svg');
  svg.setAttribute('xmlns',NS); svg.setAttribute('viewBox','-48 -22 120 126');
  svg.setAttribute('role','img'); svg.setAttribute('aria-label','Your TikZ penguin');
  const drawing = document.createElementNS(NS,'g'); drawing.setAttribute('data-drawing','');
  const layers = [];
  for (const id of selectedParts(state,catalog)) {
    const part = pack.get(id);
    if (!part) throw new Error('Missing drawing part: '+id);
    for (const original of part.children) {
      const clone = original.cloneNode(true);
      clone.setAttribute('data-part',id);
      for (const e of [clone,...clone.querySelectorAll('*')]) {
        for (const a of [...e.attributes]) {
          if (a.name === 'id') e.setAttribute('id',prefix+a.value);
          else if (a.value.includes('url(#')) e.setAttribute(a.name,a.value.replace(/url\(#([^)]*)\)/g,(_,id) => 'url(#'+prefix+id+')'));
          else if ((a.localName === 'href') && a.value.startsWith('#')) e.setAttributeNS(a.namespaceURI,a.name,'#'+prefix+a.value.slice(1));
        }
        for (const attr of ['fill','stroke']) {
          const role = e.getAttribute('data-'+attr);
          if (role) e.setAttribute(attr,state.colors[role]);
        }
      }
      layers.push(clone);
    }
  }
  layers.sort((a,b) => Number(a.getAttribute('data-z'))-Number(b.getAttribute('data-z')));
  drawing.append(...layers); svg.append(drawing);
  return svg;
}

// Measure a fresh, static drawing, independently of the animated preview's
// viewport, CSS transitions, ghost parts, or current wing animation frame.
export function exportDrawing(pack, state, catalog) {
  const svg = compose(pack,state,catalog,'export-');
  const host = document.createElement('div');
  host.setAttribute('aria-hidden','true');
  host.style.cssText = 'position:fixed;left:-10000px;top:0;width:1px;height:1px;visibility:hidden;pointer-events:none';
  host.append(svg); document.body.append(host);
  try {
    const bounds = svg.querySelector('[data-drawing]').getBBox(), pad = 9;
    if (bounds.width > 0 && bounds.height > 0) {
      svg.setAttribute('viewBox',[bounds.x-pad,bounds.y-pad,bounds.width+2*pad,bounds.height+2*pad].join(' '));
    }
    return svg;
  } finally {svg.remove();host.remove();}
}

export function serialize(svg) {
  const clone = svg.cloneNode(true);
  clone.removeAttribute('class'); clone.removeAttribute('aria-label'); clone.removeAttribute('role');
  // Shadows and idle animations belong to the editor, not the exported drawing.
  for (const node of clone.querySelectorAll('[data-decor]')) node.remove();
  for (const node of clone.querySelectorAll('[data-unwrap]')) node.replaceWith(...node.childNodes);
  for (const node of [clone,...clone.querySelectorAll('*')]) {
    for (const attr of [...node.attributes]) if (attr.name.startsWith('data-')) node.removeAttribute(attr.name);
  }
  return '<?xml version="1.0" encoding="UTF-8"?>\n'+new XMLSerializer().serializeToString(clone);
}
