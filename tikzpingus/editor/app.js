import {NS,PALETTES,defaults,normalize,update,encode,decode,isShareHash,tex,parsePack,compose,exportDrawing,serialize} from './__CORE__';

const editor = document.getElementById('pingu-editor');
const $ = id => editor.querySelector('#'+id);
const storageKey = 'tikzpingus-builder-v1';
const TABS = ['body','pose','face','style','colors'];
const motion = !matchMedia('(prefers-reduced-motion: reduce)').matches;
const packs = new Map(), requests = new Map(), stale = new Set(TABS);
let catalog, state, activeTab = 'pose', activePreset = '', scene, rendering = 0, toastTimer, thumbTimer;
let counter = 0, shown = null, drawn = 0, past = [], future = [], lastEdit = {key:'',time:0};

// Viewport crops for the tile thumbnails, in drawing coordinates.
const CROPS = {eyes:'-20 5 70 49', eyewear:'-20 5 70 49', bill:'-8 20 40 34', feet:'-17 73 58 22',
  headwear:'-31 -35 90 100', neckwear:'-26 1 80 95', clothing:'-28 0 84 102', belly:'-26 1 80 95', wing:'-34 -4 92 100'};
const PRESET_ICONS = {classic:'🐧', hello:'👋', cosy:'☕', graduate:'🎓', royal:'👑', musician:'🎸', work:'💻'};

function toast(message, icon = '✓') {
  clearTimeout(toastTimer);
  const notice = $('notice');
  notice.replaceChildren(element('span',{class:'toast-icon','aria-hidden':'true'},icon),document.createTextNode(message));
  notice.classList.remove('show'); void notice.offsetWidth; notice.classList.add('show');
  toastTimer = setTimeout(() => {notice.classList.remove('show'); notice.replaceChildren();},3200);
}

function element(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [key,value] of Object.entries(attrs)) e.setAttribute(key,value);
  if (text !== undefined) e.textContent = text;
  return e;
}

function svgElement(tag, attrs = {}) {
  const e = document.createElementNS(NS,tag);
  for (const [key,value] of Object.entries(attrs)) e.setAttribute(key,value);
  return e;
}

function documentationKey(key) {
  const fixed = {body:'body type',feet:'feet',eyes:'eyes',bill:'bill',hair:'hairstyle'};
  if (fixed[key]) {
    const choice = key === 'hair' ? (state.hair ? '' : 'none') : state[key];
    const alias = fixed[key]+' '+choice;
    return catalog.documentation.keys[alias] ? alias : fixed[key];
  }
  if (key.startsWith('color:')) return catalog.colors.find(c => c.id === key.slice(6))?.tex;
  if (key.endsWith('Wing')) {
    const side = key.slice(0,-4), item = catalog.items.find(c => c.id === state[side+'Item']);
    if (item?.tex) return item.tex+' '+side;
    const alias = side+' wing '+state[key];
    return catalog.documentation.keys[alias] ? alias : side+' wing';
  }
  return catalog[key]?.find(c => c.id === state[key])?.tex;
}

function updateDocumentation(link) {
  const key = link.dataset.doc, name = documentationKey(key);
  const href = catalog.documentation.keys[name] || catalog.documentation.groups[key];
  if (!href) {link.hidden = true;return;}
  link.hidden = false;
  link.href = new URL(href,new URL('../',import.meta.url)).href;
  link.title = 'Documentation: '+(name || link.dataset.docLabel)+' (opens in a new tab)';
  link.setAttribute('aria-label',link.title);
}

function documentationLink(key, label) {
  const link = element('a',{class:'doc-info','data-doc':key,'data-doc-label':label,target:'_blank',rel:'noopener'});
  const icon = svgElement('svg',{viewBox:'0 0 16 16','aria-hidden':'true',focusable:'false'});
  icon.append(svgElement('path',{d:'M8 4C6 2.6 4 2.3 1.5 2.8v9.5C4 11.8 6 12.1 8 13.5c2-1.4 4-1.7 6.5-1.2V2.8C12 2.3 10 2.6 8 4Zm0 0v9.5'}));
  link.append(icon);updateDocumentation(link);return link;
}

async function loadPack(body) {
  if (packs.has(body)) return packs.get(body);
  if (!requests.has(body)) requests.set(body,(async () => {
    const response = await fetch(new URL(catalog.packs[body],import.meta.url));
    if (!response.ok) throw new Error('Could not load the drawing parts. Please try again.');
    const pack = parsePack(await response.text()); packs.set(body,pack); return pack;
  })().catch(error => {requests.delete(body);throw error;}));
  return requests.get(body);
}

/* ---------- Controls ---------- */

const options = (key, family) => catalog[family].map(c => ({key, value:c.id, label:c.label}));

// One grid per wing: poses first, then the things it can hold (which imply the grab pose).
function wingOptions(side) {
  const wing = side+'Wing', item = side+'Item', label = id => catalog.wings.find(c => c.id === id).label;
  return [
    ...catalog.wings.filter(c => !['grab','none'].includes(c.id)).map(c => ({key:wing, value:c.id, label:c.label})),
    ...catalog.items.filter(c => c.id !== 'none').map(c => ({key:item, value:c.id, label:c.label})),
    {key:wing, value:'grab', label:'Open grip'}, {key:wing, value:'none', label:label('none')}];
}

function tiles(panel, label, list, {cols = 3, hint} = {}) {
  const field = element('fieldset',{class:'control-group'}), legend = element('legend',{},label);
  if (hint) legend.append(element('small',{},hint));
  if (list.length) legend.append(documentationLink(list[0].key,label));
  const grid = element('div',{class:'choices cols-'+cols});
  for (const o of list) {
    const button = element('button',{type:'button',class:'choice','data-key':o.key,'data-value':o.value,
      'aria-label':label+': '+o.label,'aria-pressed':'false'});
    button.append(element('span',{class:'thumbnail','aria-hidden':'true'}),element('span',{class:'choice-label'},o.label));
    grid.append(button);
  }
  field.append(legend,grid); panel.append(field);
}

function group(panel, label, docKey, ...children) {
  const field = element('fieldset',{class:'control-group'});
  const legend = element('legend',{},label);legend.append(documentationLink(docKey,label));
  field.append(legend,...children); panel.append(field); return field;
}

function controls() {
  $('panels').replaceChildren();
  const panels = {};
  for (const name of TABS) {
    const panel = element('section',{id:'panel-'+name,role:'tabpanel','aria-labelledby':'tab-'+name,tabindex:'0'});
    panel.hidden = name !== activeTab; panels[name] = panel; $('panels').append(panel);
  }
  tiles(panels.body,'Body shape',options('body','bodies'));
  tiles(panels.body,'Feet',options('feet','feet'));
  const hair = element('label',{class:'switch-row'});
  hair.append(element('span',{},'Show hair'),element('input',{type:'checkbox',class:'switch','data-key':'hair'}));
  group(panels.body,'Hair','hair',hair);

  tiles(panels.pose,'Left wing',wingOptions('left'),{cols:4});
  tiles(panels.pose,'Right wing',wingOptions('right'),{cols:4});

  tiles(panels.face,'Expression',options('eyes','eyes'),{cols:4});
  tiles(panels.face,'Bill',options('bill','bills'),{cols:4});
  tiles(panels.face,'Eyewear',options('eyewear','eyewear'));

  tiles(panels.style,'Clothes',options('clothing','clothing'),{cols:4});
  tiles(panels.style,'Headwear',options('headwear','headwear'));
  tiles(panels.style,'Around the neck',options('neckwear','neckwear'),{cols:4});
  tiles(panels.style,'Extras',options('belly','belly'));

  const paletteBox = element('div',{class:'palette-list'});
  for (const [label,values] of PALETTES) {
    const button = element('button',{type:'button',class:'palette','aria-pressed':'false','data-palette':values.join()});
    const swatch = element('span',{class:'swatch','aria-hidden':'true'});
    for (const color of [values[0],values[1],values[3]]) swatch.append(element('i',{style:'background:'+color}));
    button.append(swatch,element('span',{},label));
    button.addEventListener('click',() => {
      commit('palette'); state = {...state,colors:Object.fromEntries(catalog.colors.map((c,i) => [c.id,values[i]]))};
      activePreset = ''; changed();
    });
    paletteBox.append(button);
  }
  group(panels.colors,'Palette','colors',paletteBox);
  const fields = element('div',{class:'color-list'});
  for (const c of catalog.colors) {
    const row = element('div',{class:'color-row'}), id = 'color-'+c.id;
    row.append(element('input',{type:'color',id,'data-key':'color:'+c.id,'aria-label':c.label+' color'}),
      element('label',{for:id},c.label),element('input',{type:'text','data-color-text':c.id,'aria-label':c.label+' hex color',maxlength:'7',spellcheck:'false',autocomplete:'off',pattern:'#[0-9a-fA-F]{6}'}));
    fields.append(row);
  }
  const resetColors = element('button',{type:'button',class:'secondary small'},'Reset colors');
  resetColors.addEventListener('click',() => {commit('colors');state = {...state,colors:defaults(catalog).colors};activePreset = '';changed();});
  group(panels.colors,'Colors','colors',fields,resetColors);

  $('panels').addEventListener('click',event => {
    const button = event.target.closest('button[data-key]');
    if (!button) return;
    const {key,value} = button.dataset;
    commit(key);
    // Picking a pose (even the empty grip) puts down whatever that wing was holding.
    state = update(state,key,value,catalog);
    if (key.endsWith('Wing')) state = update(state,key.replace('Wing','Item'),'none',catalog);
    activePreset = ''; changed();
    if (motion) {button.classList.remove('picked'); void button.offsetWidth; button.classList.add('picked');}
  });
  $('panels').addEventListener('input',event => {
    const input = event.target;
    if (input.matches('input[data-key]')) set(input.dataset.key,input.type === 'checkbox' ? input.checked : input.value);
    else if (input.matches('[data-color-text]')) {
      const value = input.value.startsWith('#') ? input.value : '#'+input.value;
      const valid = /^#[0-9a-f]{6}$/i.test(value);
      input.setAttribute('aria-invalid',String(!valid));
      if (valid) set('color:'+input.dataset.colorText,value.toLowerCase(),input);
    }
  });
  $('panels').addEventListener('focusout',event => {
    const input = event.target;
    if (input.matches('[data-color-text]')) {input.value = state.colors[input.dataset.colorText];input.removeAttribute('aria-invalid');}
  });
}

function pressed(key, value) {
  if (key.endsWith('Wing')) return state[key] === value && state[key.replace('Wing','Item')] === 'none';
  return state[key] === value;
}

function sync(skip) {
  for (const link of editor.querySelectorAll('a[data-doc]')) updateDocumentation(link);
  for (const e of $('panels').querySelectorAll('[data-key]')) {
    const key = e.dataset.key, value = key.startsWith('color:') ? state.colors[key.slice(6)] : state[key];
    if (e.matches('button')) e.setAttribute('aria-pressed',String(pressed(key,e.dataset.value)));
    else if (e.type === 'checkbox') e.checked = value;
    else if (e !== document.activeElement || e.type === 'color') e.value = value;
  }
  for (const e of $('panels').querySelectorAll('[data-color-text]')) if (e !== skip && e !== document.activeElement) e.value = state.colors[e.dataset.colorText];
  const colors = catalog.colors.map(c => state.colors[c.id]).join();
  for (const e of $('panels').querySelectorAll('[data-palette]')) e.setAttribute('aria-pressed',String(e.dataset.palette === colors));
  for (const e of $('presets').children) e.setAttribute('aria-pressed',String(e.dataset.preset === activePreset));
  $('undo').disabled = !past.length; $('redo').disabled = !future.length;
}

/* ---------- History ---------- */

// Record the state before an edit. Rapid edits of one control (dragging a
// color, typing a hex value) collapse into a single undo step.
function commit(key = '') {
  const now = Date.now();
  if (key && key === lastEdit.key && now-lastEdit.time < 800) {lastEdit.time = now; return;}
  lastEdit = {key,time:now};
  past.push(state); if (past.length > 100) past.shift(); future = [];
}

function travel(from, to, message) {
  if (!from.length) return;
  to.push(state); state = from.pop(); lastEdit = {key:'',time:0};
  activePreset = ''; changed(); toast(message,'↺');
}

function set(key, value, input) {
  commit(key); state = update(state,key,value,catalog); activePreset = '';
  changed(input);
}

function changed(input) {
  sync(input);
  try {localStorage.setItem(storageKey,JSON.stringify(state));} catch {}
  // Keep copied links in sync without adding an entry for every edit.
  if (isShareHash(location.hash)) history.replaceState(null,'',encode(state));
  cancelAnimationFrame(rendering); rendering = requestAnimationFrame(render);
}

/* ---------- Drawing ---------- */

function miniature(pack, next, viewBox) {
  const svg = compose(pack,next,catalog,'thumb-'+(++counter)+'-');
  svg.setAttribute('aria-hidden','true'); svg.removeAttribute('aria-label'); svg.removeAttribute('role');
  svg.setAttribute('focusable','false'); svg.setAttribute('viewBox',viewBox);
  return svg;
}

// What the pingu would look like with one choice swapped in.
function tryOn(key, value) {
  let next = update(state,key,value,catalog);
  if (key.endsWith('Wing')) next = update(next,key.replace('Wing','Item'),'none',catalog);
  return next;
}

function thumbnails(name) {
  const pack = packs.get(state.body), panel = $('panel-'+name);
  if (!pack || !panel) return;
  stale.delete(name);
  for (const button of panel.querySelectorAll('.choice')) {
    const {key,value} = button.dataset, thumb = button.querySelector('.thumbnail');
    if (key === 'body') {
      if (!thumb.firstChild) thumb.append(element('img',{src:new URL(catalog.bodies.find(c => c.id === value).thumbnail,import.meta.url).href,alt:'',width:'80',height:'95'}));
      continue;
    }
    const crop = CROPS[/^(left|right)(Wing|Item)$/.test(key) ? 'wing' : key] || CROPS.neckwear;
    try {thumb.replaceChildren(miniature(pack,tryOn(key,value),crop));} catch {thumb.replaceChildren();}
  }
}

function union(nodes) {
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const node of nodes) {
    const b = node.getBBox(); if (!b.width && !b.height) continue;
    x0 = Math.min(x0,b.x); y0 = Math.min(y0,b.y); x1 = Math.max(x1,b.x+b.width); y1 = Math.max(y1,b.y+b.height);
  }
  return x0 < x1 ? {x:x0,y:y0,width:x1-x0,height:y1-y0} : null;
}

// Editor-only flourishes, marked data-decor so exports drop them.
function decorate(svg, bounds) {
  const body = union(svg.querySelectorAll('[data-part$="-bodytype"]')) || bounds;
  svg.insertBefore(svgElement('ellipse',{'data-decor':'',class:'ground',cx:body.x+body.width/2,
    cy:bounds.y+bounds.height-1.5,rx:body.width*.52,ry:3.6}),svg.firstChild);
  if (!motion) return;
  if (['normal','shiny','vertical','sad','critical'].includes(state.eyes)) svg.classList.add('blinks');
  for (const side of ['left','right']) if (state[side+'Wing'] === 'wave') wave(svg,side);
}

// Two quick waves, then a rest.
function wave(svg, side) {
  const sign = side === 'left' ? 1 : -1;
  motions[side].push({angles:[0,-12,0,-12,0,0].map(a => a*sign),
    timing:{keyTimes:'0;.07;.14;.21;.28;1',dur:'6s',begin:'.8s',repeatCount:'indefinite'}});
}

/* ---------- Wing swings ---------- */

// Each wing is an ellipse cut by a clip path that follows the body, so its
// root blends into the body edge. To swing a wing we rotate only the ellipse
// and leave the clip in place, which keeps the root trimmed at the body.
// Shifted copies of the ellipse extend it toward the body as it turns, so no
// gap opens; the shift is zero at rest. The package's small fillets between
// wing and body are handled below.

const drawingOf = svg => svg.querySelector('[data-drawing]');
const wingParts = (svg, side) => [...svg.querySelectorAll(`[data-drawing] > [data-part$="-${side}wing"]:not([data-decor])`)];
const wingShapes = part => [...part.querySelectorAll('path,circle,ellipse,rect,polygon')].filter(e => !e.closest('defs,clipPath'));
const matrix = m => `matrix(${m.a} ${m.b} ${m.c} ${m.d} ${m.e} ${m.f})`;

// Where the wing meets the body: sample a vertical line just inside the
// body's outer edge and find where the wing covers it.
function shoulder(svg, side) {
  const body = union(svg.querySelectorAll('[data-part$="-bodytype"]'));
  const shapes = wingParts(svg,side).flatMap(wingShapes);
  const root = drawingOf(svg).getScreenCTM()?.inverse();
  if (!body || !shapes.length || !root) return null;
  const local = shapes.map(shape => [shape,root.multiply(shape.getScreenCTM()).inverse()]);
  const x = side === 'left' ? body.x+body.width*.9 : body.x+body.width*.1;
  let top = null, bottom = null;
  for (let y = body.y; y <= body.y+body.height; y += .75) {
    const hit = local.some(([shape,m]) => {
      const point = new DOMPoint(x,y).matrixTransform(m);
      return shape.isPointInFill(point) || shape.isPointInStroke(point);
    });
    if (hit) {top ??= y; bottom = y;}
  }
  return top === null ? null : {x, y:top+Math.min(5,(bottom-top)/2)};
}

// Direction the wing points, seen from the shoulder, in degrees.
function heading(svg, side, pivot) {
  const box = union(wingParts(svg,side));
  return box && Math.atan2(box.y+box.height/2-pivot.y,box.x+box.width/2-pivot.x)*180/Math.PI;
}

// Swing a wing through one or more motions ({angles, timing}; degrees in
// drawing coordinates). Motions share one set of wrappers and add together.
const motions = {left:[], right:[]};

function swing(svg, side, list) {
  const pivot = shoulder(svg,side), root = drawingOf(svg).getScreenCTM()?.inverse();
  if (!pivot || !root || !list.length) return null;
  const animate = (node, type, values) => {
    for (const motion of list) {
      const {angles,timing} = motion;
      node.append(svgElement('animateTransform',{'data-decor':'',attributeName:'transform',type,
      additive:'sum',values:angles.map((a,n) => values(a,motion,n)).join(';'),
      ...(timing.calcMode === 'linear' ? {} : {calcMode:'spline',keySplines:Array(angles.length-1).fill('.3 .7 .4 1').join(';')}),...timing}));
    }
  };
  const turn = node => animate(node,'rotate',a => `${a} ${pivot.x} ${pivot.y}`);
  const group = (attrs = {}) => svgElement('g',attrs);
  const inward = side === 'left' ? -1 : 1;
  const direction = (shape, m) => {
    const b = shape.getBBox(), c = new DOMPoint(b.x+b.width/2,b.y+b.height/2).matrixTransform(m);
    return Math.atan2(c.y-pivot.y,c.x-pivot.x)*180/Math.PI;
  };
  for (const part of wingParts(svg,side)) {
    const shapes = wingShapes(part).map(shape => {
      const b = shape.getBBox(), local = root.multiply(shape.parentNode.getScreenCTM());
      return {shape, local, area:b.width*b.height, heading:direction(shape,root.multiply(shape.getScreenCTM()))};
    });
    const main = shapes.reduce((a,b) => b.area > a.area ? b : a);
    for (const {shape,local,area,heading} of shapes) {
      if (area < main.area*.25) {
        // A fillet rounding the corner between wing and body. The one on the
        // shoulder side stays put. The one in the armpit turns with the wing
        // as the armpit closes, and fans out between rest and the wing as it
        // opens, turning about its far tip on the body outline so that end
        // stays put. While a new pose swings in, both wait inside that tip and
        // grow out as the wing arrives, so they never read as a second arm.
        // At rest both are exactly the original.
        const offset = ((heading-main.heading+540)%360)-180, armpit = offset*(side === 'left' ? 1 : -1) >= 0;
        const m = root.multiply(shape.getScreenCTM()), length = shape.getTotalLength?.() || 0;
        let tip = pivot, far = 0;
        for (let n = 0; n <= 48; n++) {
          const q = shape.getPointAtLength(length*n/48).matrixTransform(m), d = Math.hypot(q.x-pivot.x,q.y-pivot.y);
          if (d > far) {far = d; tip = q;}
        }
        const outer = group({'data-unwrap':'',transform:matrix(local.inverse())});
        shape.replaceWith(outer);
        const shares = armpit ? Array.from({length:13},(_,n) => n/12) : [1];
        shares.forEach((share,n) => {
          const last = n === shares.length-1, wrap = attrs => group(last ? {'data-unwrap':'',...attrs} : attrs);
          const spin = last ? group({'data-unwrap':''}) : group({'data-decor':''});
          const to = wrap({transform:`translate(${tip.x} ${tip.y})`}), size = wrap(), back = wrap({transform:`translate(${-tip.x} ${-tip.y})`});
          const inner = wrap({transform:matrix(local)});
          if (armpit) animate(spin,'rotate',a => a*offset < 0 ? `${share*a} ${tip.x} ${tip.y}` : `${a} ${pivot.x} ${pivot.y}`);
          // While a new pose swings in, the fillets belong to a wing that has
          // not arrived yet: keep them out of sight until it is nearly there.
          animate(size,'scale',(a,motion,n) => motion.fillets?.[n] ?? 1);
          inner.append(last ? shape : shape.cloneNode(true)); back.append(inner); size.append(back); to.append(size); spin.append(to); outer.append(spin);
        });
        continue;
      }
      // Rotate in drawing coordinates: undo the shape's own transform, turn,
      // then reapply it. These wrappers multiply out to nothing and are
      // unwrapped on export.
      const outer = group({'data-unwrap':'',transform:matrix(local.inverse())});
      shape.replaceWith(outer);
      for (const share of [1,.8,.6,.4,.2]) {
        const shift = group({'data-decor':''}), spin = group(), inner = group({transform:matrix(local)});
        animate(shift,'translate',a => `${inward*Math.min(6,share*.15*Math.abs(a))} 0`);
        turn(spin); inner.append(shape.cloneNode(true)); spin.append(inner); shift.append(spin); outer.append(shift);
      }
      const spin = group({'data-unwrap':''}), inner = group({'data-unwrap':'',transform:matrix(local)});
      turn(spin); inner.append(shape); spin.append(inner); outer.append(spin);
    }
  }
  // Whatever the wing holds turns with it.
  for (const item of svg.querySelectorAll(`[data-drawing] > [data-part^="item-${side}-"]`)) turn(item);
  return pivot;
}

/* ---------- Change animations ---------- */

// Each kind of change gets its own entrance: hats drop on, glasses slide
// down, eyes blink open, wings swing over, things held pop into view.
const ENTRANCES = {
  clothing:['a-pop',s => `[data-part^="clothing-${s.clothing}-"]`],
  headwear:['a-drop',s => `[data-part="headwear-${s.headwear}-extra"]`],
  eyewear:['a-slide',s => `[data-part="eyewear-${s.eyewear}-extra"]`],
  neckwear:['a-pop',s => `[data-part="neckwear-${s.neckwear}-extra"]`],
  belly:['a-pop',s => `[data-part="belly-${s.belly}-extra"]`],
  leftItem:['a-pop',s => `[data-part="item-left-${s.leftItem}-extra"]`],
  rightItem:['a-pop',s => `[data-part="item-right-${s.rightItem}-extra"]`],
  eyes:['a-blink',() => '[data-part$="lefteye"],[data-part$="righteye"]'],
  bill:['a-pop',() => '[data-part$="-bill"]'],
  feet:['a-tap',() => '[data-part$="foot"]'],
  hair:['a-sprout',() => '[data-part="base-hairstyle"]']};
const EMPTY = new Set(['none',false]);
let zoom = 0;

function fadeOut(node, then = () => node.remove()) {
  node.animate([{opacity:1},{opacity:0}],{duration:260,easing:'ease-out',fill:'forwards'}).onfinish = then;
}

// Accessories, wings and hair that were taken away fade out where they were,
// layered at their original depth. Swapped eyes, bills and feet are covered
// by their own entrance instead.
function ghosts(old) {
  const drawing = scene.querySelector('[data-drawing]'), kept = new Set([...drawing.children].map(e => e.dataset.part));
  for (const part of old.querySelectorAll('[data-drawing] > [data-part]:not([data-decor])')) {
    const id = part.dataset.part;
    if (kept.has(id) || !/(-extra|wing|hairstyle|clothingbehind|clothingmiddle|clothingmain)$/.test(id)) continue;
    // A wing that changes pose swings over rather than fading.
    const side = id.match(/-(left|right)wing$/)?.[1];
    if (side && state[side+'Wing'] !== 'none') continue;
    const ghost = part.cloneNode(true), z = Number(ghost.dataset.z);
    ghost.setAttribute('data-decor','');
    for (const node of ghost.querySelectorAll('animate,animateTransform')) node.remove();
    drawing.insertBefore(ghost,[...drawing.children].find(e => Number(e.dataset.z) > z) || null);
    fadeOut(ghost);
  }
}

// Ease the frame to the new size, so adding a tall hat zooms out smoothly.
function resize(svgs, from, to) {
  cancelAnimationFrame(zoom);
  const a = from.split(/[\s,]+/).map(Number), b = to.split(/[\s,]+/).map(Number), start = performance.now();
  const step = now => {
    const t = Math.min(1,(now-start)/450), e = 1-(1-t)**3;
    const box = a.map((v,i) => v+(b[i]-v)*e).join(' ');
    for (const svg of svgs) if (svg.isConnected) svg.setAttribute('viewBox',box);
    if (t < 1) zoom = requestAnimationFrame(step);
  };
  for (const svg of svgs) svg.setAttribute('viewBox',from);
  zoom = requestAnimationFrame(step);
}

// The new wing starts out pointing where the old one did and swings into place.
function swingIn(side, headings) {
  const pivot = shoulder(scene,side), now = pivot && heading(scene,side,pivot), before = headings[side];
  if (now == null || before == null) {
    for (const part of wingParts(scene,side)) part.classList.add('a-fade');
    return;
  }
  let start = ((before-now+540)%360)-180;
  start = Math.max(-70,Math.min(70,start));
  if (Math.abs(start) < 6) start = (side === 'left' ? 1 : -1)*10;
  // Sample an ease-out with a slight overshoot densely, so that everything
  // derived from the angle (fillet sizes, fan spread) follows it exactly.
  const steps = 24, back = 1.2;
  const ease = t => 1+(back+1)*(t-1)**3+back*(t-1)**2;
  const times = Array.from({length:steps+1},(_,n) => n/steps);
  const angles = times.map(t => start*(1-ease(t)));
  // Fillets grow in once the wing first comes within a few degrees of rest
  // and then stay, even while it overshoots and settles back.
  let grown = 0;
  const fillets = angles.map(a => (grown = Math.max(grown,Math.min(1,(2.5-Math.abs(a))/2))));
  motions[side].push({angles,fillets,
    timing:{calcMode:'linear',keyTimes:times.map(t => +t.toFixed(4)).join(';'),dur:'.6s',fill:'remove'}});
}

function animateChange(prev, next, old, headings = {}) {
  const keys = Object.keys(next).filter(k => k !== 'colors' && prev[k] !== next[k]);
  const colors = Object.keys(next.colors).filter(k => prev.colors[k] !== next.colors[k]).length;
  if (!keys.length && !colors) return;
  for (const key of keys) {
    if (key.endsWith('Wing')) {
      if (next[key] !== 'none') swingIn(key.slice(0,-4),headings);
      continue;
    }
    const entrance = ENTRANCES[key];
    if (!entrance || EMPTY.has(next[key])) continue;
    for (const part of scene.querySelectorAll(entrance[1](next))) part.classList.add(entrance[0]);
  }
  if (keys.includes('body')) scene.classList.add('a-morph');
  if (!old) return;
  const from = old.getAttribute('viewBox'), to = scene.getAttribute('viewBox'), moving = [scene];
  // A new body shape or palette changes everything at once: cross-fade the
  // whole drawing. Otherwise only the parts that went away fade.
  if (keys.includes('body') || colors > 1) {
    old.classList.add('leaving'); old.setAttribute('aria-hidden','true'); old.removeAttribute('role');
    for (const node of old.querySelectorAll('animate,animateTransform')) node.remove();
    $('preview').append(old); fadeOut(old); moving.push(old);
  } else ghosts(old);
  if (from && to && from !== to) resize(moving,from,to);
}

async function render() {
  const body = state.body;
  $('workspace').setAttribute('aria-busy','true');
  for (const id of ['svg','png','copy']) $(id).disabled = true;
  try {
    const pack = await loadPack(body);
    if (state.body !== body) return;
    const old = $('preview').querySelector('svg.pingu:not(.leaving)');
    // Note where each wing pointed before the old drawing leaves the page.
    const headings = {};
    if (old && motion) for (const side of ['left','right']) {
      const pivot = shoulder(old,side);
      if (pivot) headings[side] = heading(old,side,pivot);
    }
    // A fresh ID prefix per drawing keeps fading copies' clip paths their own.
    scene = compose(pack,state,catalog,'preview-'+(++drawn)+'-');
    scene.classList.add('pingu');
    scene.addEventListener('animationend',event => {
      const target = event.target;
      if (target.matches('[data-drawing]')) scene.classList.remove(...BOOPS);
      target.classList.remove(...[...target.classList].filter(c => c.startsWith('a-')));
      if (!target.classList.length) target.removeAttribute('class');
    });
    $('preview').replaceChildren(scene);
    // Fit the drawing after insertion, leaving breathing room for tall hats.
    motions.left = []; motions.right = [];
    const bounds = scene.querySelector('[data-drawing]').getBBox();
    if (bounds.width > 0 && bounds.height > 0) {
      const pad = 9; scene.setAttribute('viewBox',[bounds.x-pad,bounds.y-pad,bounds.width+2*pad,bounds.height+2*pad].join(' '));
      decorate(scene,bounds);
    }
    if (motion && shown) animateChange(shown,state,old,headings);
    if (motion) for (const side of ['left','right']) swing(scene,side,motions[side]);
    else cancelAnimationFrame(zoom);
    shown = state; markFavorite();
    showCode();
    for (const name of TABS) stale.add(name);
    clearTimeout(thumbTimer); thumbTimer = setTimeout(() => thumbnails(activeTab),40);
    for (const id of ['svg','png','copy','share','reset','shuffle']) $(id).disabled = false;
  } catch (error) {
    $('preview').replaceChildren(element('p',{class:'error'},error.message));
    const retry = element('button',{class:'secondary'},'Try again'); retry.addEventListener('click',() => render()); $('preview').append(retry);
    for (const id of ['svg','png','copy']) $(id).disabled = true;
  } finally {if (state.body === body) $('workspace').setAttribute('aria-busy','false');}
}

// A few different reactions to a poke, never the same one twice in a row.
const BOOPS = ['boop-hop','boop-wiggle','boop-spin','boop-love'];
let lastBoop = '';

function boop() {
  if (!scene || !motion) return;
  const choices = BOOPS.filter(b => b !== lastBoop), kind = choices[Math.floor(Math.random()*choices.length)];
  lastBoop = kind;
  scene.classList.remove('a-morph',...BOOPS); void scene.getBoundingClientRect(); scene.classList.add(kind);
  for (const eye of scene.querySelectorAll('[data-drawing] > [data-part$="eye"]')) {
    eye.classList.remove('a-blink'); void eye.getBoundingClientRect(); eye.classList.add('a-blink');
  }
  if (kind === 'boop-love') {
    const box = scene.querySelector('[data-drawing]').getBoundingClientRect();
    confetti({getBoundingClientRect:() => new DOMRect(box.left+box.width*.5,box.top+box.height*.2,0,0)},true);
  }
}

/* ---------- Favorites ---------- */

const favoritesKey = 'tikzpingus-favorites-v1', MAX_FAVORITES = 30;
let favorites = [];
const fingerprint = s => JSON.stringify(normalize(s,catalog));

function loadFavorites() {
  try {
    const saved = JSON.parse(localStorage.getItem(favoritesKey));
    if (Array.isArray(saved)) favorites = saved.slice(0,MAX_FAVORITES).map(s => normalize(s,catalog));
  } catch {}
}

function storeFavorites() {try {localStorage.setItem(favoritesKey,JSON.stringify(favorites));} catch {}}

function toggleFavorite() {
  const key = fingerprint(state), index = favorites.findIndex(f => fingerprint(f) === key);
  if (index >= 0) {favorites.splice(index,1); toast('Removed from your favorites.','♡');}
  else {
    favorites.unshift(state); favorites.length = Math.min(favorites.length,MAX_FAVORITES);
    confetti($('favorite'),true); toast('Saved to your favorites.','♥');
  }
  storeFavorites(); showFavorites(index < 0 ? key : null);
}

function showFavorites(fresh) {
  $('favorites').hidden = !favorites.length;
  $('favorite-count').textContent = favorites.length;
  $('favorite-list').replaceChildren(...favorites.map((saved,n) => {
    const key = fingerprint(saved), item = element('li',{class:'favorite'+(key === fresh ? ' fresh' : ''),'data-fingerprint':key});
    const open = element('button',{type:'button',class:'favorite-open','aria-label':'Open favorite '+(n+1)});
    const remove = element('button',{type:'button',class:'favorite-remove','aria-label':'Remove favorite '+(n+1),title:'Remove'},'×');
    open.addEventListener('click',() => {
      if (fingerprint(state) === key) {boop(); return;}
      commit(); state = normalize(saved,catalog); activePreset = ''; changed();
    });
    remove.addEventListener('click',() => {
      favorites = favorites.filter(f => fingerprint(f) !== key); storeFavorites(); showFavorites();
    });
    item.append(open,remove); drawFavorite(open,saved);
    return item;
  }));
  markFavorite();
}

async function drawFavorite(button, saved) {
  try {
    const svg = compose(await loadPack(saved.body),saved,catalog,'favorite-'+(++counter)+'-');
    svg.setAttribute('aria-hidden','true'); svg.removeAttribute('role'); svg.removeAttribute('aria-label');
    button.replaceChildren(svg);
    const b = svg.querySelector('[data-drawing]').getBBox();
    if (b.width) svg.setAttribute('viewBox',[b.x-4,b.y-4,b.width+8,b.height+8].join(' '));
  } catch {}
}

function markFavorite() {
  if (!catalog || !state) return;
  const key = fingerprint(state), saved = favorites.some(f => fingerprint(f) === key), button = $('favorite');
  button.setAttribute('aria-pressed',String(saved));
  button.title = saved ? 'Remove from favorites' : 'Save to favorites';
  button.querySelector('.favorite-label').textContent = saved ? 'Saved' : 'Save';
  for (const item of $('favorite-list').children) item.classList.toggle('current',item.dataset.fingerprint === key);
}

/* ---------- Code ---------- */

// Light TeX highlighting: commands, option keys, values and punctuation.
function highlight(text) {
  const out = document.createDocumentFragment();
  let inValue = false, key = '';
  for (const [token] of text.matchAll(/\\[A-Za-z@]+|%|[{}[\],=]|[^\\%{}[\],=]+/g)) {
    let cls = '', href;
    if (token[0] === '\\') {cls = 'tok-cmd';href = catalog.documentation.keys[token];}
    else if (token === '%') cls = 'tok-comment';
    else if (token === '=') {cls = 'tok-punct'; inValue = true;}
    else if (/^[{}[\],]$/.test(token)) {cls = 'tok-punct'; if (token !== '{' && token !== '}') inValue = false;}
    else if (token.trim()) {
      cls = inValue ? 'tok-value' : 'tok-key';
      if (inValue) href = catalog.documentation.keys[key+' '+token.trim()];
      else {key = token.trim();href = catalog.documentation.keys[key];}
    }
    if (!cls) {out.append(document.createTextNode(token));continue;}
    const span = element('span',{class:cls});
    if (href) {
      const [,leading,content,trailing] = token.match(/^(\s*)([\s\S]*?)(\s*)$/);
      span.append(document.createTextNode(leading),element('a',{class:'code-doc',
        href:new URL(href,new URL('../',import.meta.url)).href,target:'_blank',rel:'noopener',
        title:'Documentation: '+content+' (opens in a new tab)'},content),document.createTextNode(trailing));
    } else span.textContent = token;
    out.append(span);
  }
  return out;
}

function showCode() {$('code').replaceChildren(highlight(tex(state,catalog,$('document').checked)));}

/* ---------- Tabs, export, sharing ---------- */

function tab(name, focus = false) {
  activeTab = name;
  for (const e of editor.querySelectorAll('[role=tab]')) {
    const selected = e.id === 'tab-'+name; e.setAttribute('aria-selected',String(selected)); e.tabIndex = selected ? 0 : -1;
    if (selected && focus) e.focus();
  }
  for (const e of editor.querySelectorAll('[role=tabpanel]')) e.hidden = e.id !== 'panel-'+name;
  $('panels').scrollTop = 0;
  if (stale.has(name)) thumbnails(name);
}

function download(data, type, name) {
  const url = URL.createObjectURL(new Blob([data],{type})), a = element('a',{href:url,download:name});
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url),30000);
}

function confetti(origin, hearts = false) {
  if (!motion) return;
  const box = origin.getBoundingClientRect(), colors = hearts ? ['#e25a7a','#f08aa0','#c93d63'] : ['#23735b','#f3bd45','#7cc3d8','#e9837a','#182d35'];
  for (let i = 0; i < (hearts ? 9 : 18); i++) {
    const bit = element('i',{class:hearts ? 'confetti heart' : 'confetti','aria-hidden':'true'},hearts ? '♥' : undefined);
    bit.style.cssText = `left:${box.left+box.width/2}px;top:${box.top+box.height/2}px;${hearts ? 'color' : 'background'}:${colors[i%colors.length]}`;
    editor.append(bit);
    const angle = hearts ? Math.PI*(1.25+Math.random()*.5) : Math.PI*(1.05+Math.random()*.9), dist = 50+Math.random()*70;
    const fall = hearts ? -10 : 40, spin = hearts ? (Math.random()-.5)*60 : Math.random()*540;
    bit.animate([{transform:'translate(-50%,-50%) scale(1)',opacity:1},
      {transform:`translate(calc(-50% + ${Math.cos(angle)*dist}px),calc(-50% + ${Math.sin(angle)*dist+fall}px)) rotate(${spin}deg) scale(.6)`,opacity:0}],
      {duration:700+Math.random()*400,easing:'cubic-bezier(.2,.7,.3,1)'}).onfinish = () => bit.remove();
  }
}

function flash(button, text) {
  const original = button.dataset.label ??= button.innerHTML;
  button.textContent = text; button.classList.add('done');
  clearTimeout(button.flashTimer);
  button.flashTimer = setTimeout(() => {button.innerHTML = original; button.classList.remove('done');},1600);
}

async function copy(text) {
  try {await navigator.clipboard.writeText(text); return true;}
  catch {
    const area = element('textarea',{readonly:''}); area.value = text; area.style.position = 'fixed'; area.style.opacity = '0';
    document.body.append(area); area.select();
    const ok = document.execCommand('copy'); area.remove(); return ok;
  }
}

async function drawingForExport() {
  // Capture the settings now; a body-library fetch or PNG decode may finish
  // after the user has already started editing their next pingu.
  const snapshot = normalize(state,catalog);
  return exportDrawing(await loadPack(snapshot.body),snapshot,catalog);
}

async function svg() {
  if (!scene) return;
  $('svg').disabled = true;
  try {
    const drawing = await drawingForExport();
    download(serialize(drawing),'image/svg+xml','pingu.svg'); confetti($('svg'));
  } catch {toast('SVG export failed. Please try again.','!');}
  finally {$('svg').disabled = false;}
}

async function png() {
  if (!scene) return;
  $('png').disabled = true;
  let url;
  try {
    const drawing = await drawingForExport();
    url = URL.createObjectURL(new Blob([serialize(drawing)],{type:'image/svg+xml'}));
    const image = new Image(); await new Promise((resolve,reject) => {image.onload = resolve; image.onerror = reject; image.src = url;});
    const box = drawing.viewBox.baseVal, canvas = document.createElement('canvas');
    canvas.height = 1200; canvas.width = Math.round(1200*box.width/box.height);
    canvas.getContext('2d').drawImage(image,0,0,canvas.width,canvas.height);
    const blob = await new Promise(resolve => canvas.toBlob(resolve,'image/png'));
    if (!blob) throw new Error('PNG export failed');
    download(blob,'image/png','pingu.png'); confetti($('png'));
  } catch {toast('PNG export failed. Please try SVG instead.','!');}
  finally {if (url) URL.revokeObjectURL(url); $('png').disabled = false;}
}

function surprise() {
  commit();
  const pick = family => catalog[family][Math.floor(Math.random()*catalog[family].length)].id;
  const maybe = (chance, family) => Math.random() < chance ? pick(family) : 'none';
  const wing = () => {const w = pick('wings'); return w === 'none' || w === 'grab' ? 'normal' : w;};
  const next = {...state,body:pick('bodies'),eyes:pick('eyes'),leftWing:wing(),rightWing:wing(),
    headwear:maybe(.75,'headwear'),clothing:maybe(.5,'clothing'),neckwear:maybe(.5,'neckwear'),eyewear:maybe(.35,'eyewear'),
    belly:maybe(.25,'belly'),bill:Math.random() < .25 ? pick('bills') : 'normal',leftItem:'none',rightItem:'none'};
  if (Math.random() < .25) next[Math.random() < .5 ? 'leftItem' : 'rightItem'] = pick('items');
  state = normalize(next,catalog); activePreset = ''; changed();
  const dice = document.querySelector('.dice');
  if (motion) dice.animate([{transform:'rotate(0) scale(1)'},{transform:'rotate(200deg) scale(1.3)'},{transform:'rotate(360deg) scale(1)'}],{duration:500,easing:'ease-out'});
}

async function boot() {
  const response = await fetch(new URL('./__CATALOG__',import.meta.url));
  if (!response.ok) throw new Error('Could not load the editor. Please reload the page.');
  catalog = await response.json(); state = defaults(catalog);
  try {if (isShareHash(location.hash)) state = decode(location.hash,catalog); else state = normalize(JSON.parse(localStorage.getItem(storageKey)),catalog);}
  catch {toast('Settings could not be loaded.','!');}
  controls(); loadFavorites();
  for (const preset of catalog.presets) {
    const button = element('button',{class:'preset',type:'button','data-preset':preset.id,'aria-pressed':'false'});
    button.append(element('span',{'aria-hidden':'true'},PRESET_ICONS[preset.id] || '✨'),document.createTextNode(preset.label));
    button.addEventListener('click',() => {commit();state = normalize(preset.state,catalog);activePreset = preset.id;changed();});
    $('presets').append(button);
  }
  sync();
  for (const e of editor.querySelectorAll('[role=tab]')) e.addEventListener('click',() => tab(e.id.slice(4)));
  editor.querySelector('.tabs').addEventListener('keydown',event => {
    if (!['ArrowRight','ArrowLeft','Home','End'].includes(event.key)) return;
    event.preventDefault(); const i = TABS.indexOf(activeTab), n = TABS.length;
    tab(TABS[event.key === 'Home' ? 0 : event.key === 'End' ? n-1 : (i+(event.key === 'ArrowRight' ? 1 : n-1))%n],true);
  });
  document.addEventListener('keydown',event => {
    if (!editor.contains(event.target)) return;
    if (!(event.metaKey || event.ctrlKey) || event.key.toLowerCase() !== 'z' || event.altKey) return;
    if (event.target.matches('input,textarea,[contenteditable]')) return;
    event.preventDefault();
    if (event.shiftKey) travel(future,past,'Redone'); else travel(past,future,'Undone');
  });
  $('undo').addEventListener('click',() => travel(past,future,'Undone'));
  $('redo').addEventListener('click',() => travel(future,past,'Redone'));
  $('preview').addEventListener('click',boop);
  $('document').addEventListener('change',showCode);
  $('reset').addEventListener('click',() => {commit();state = defaults(catalog);activePreset = '';changed();toast('Reset.');});
  $('shuffle').addEventListener('click',surprise);
  $('favorite').addEventListener('click',toggleFavorite);
  showFavorites();
  $('share').addEventListener('click',async () => {
    const url = new URL('../',import.meta.url); url.hash = encode(state); history.replaceState(null,'',url);
    if (await copy(url.href)) toast('Link copied.');
    else toast('Copy is unavailable. The link is in the address bar.','!');
  });
  $('copy').addEventListener('click',async () => {
    if (await copy(tex(state,catalog,$('document').checked))) flash($('copy'),'Copied ✓');
    else toast('Copy is unavailable. Select and copy the code below.','!');
  });
  $('svg').addEventListener('click',svg);
  $('png').addEventListener('click',png);
  window.addEventListener('hashchange',() => {
    if (!isShareHash(location.hash)) return;
    try {const next = decode(location.hash,catalog); commit(); state = next; activePreset = ''; changed();}
    catch {toast('That Pingu link could not be read.','!');}
  });
  await render();
}

boot().catch(error => {for (const id of ['preview','panels']) $(id).replaceChildren(element('p',{class:'error'},error.message)); $('workspace').setAttribute('aria-busy','false');});
