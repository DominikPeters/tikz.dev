import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PALETTES,defaults,normalize,update,encode,decode,isShareHash,tex} from './core.mjs';
const catalog=JSON.parse(readFileSync(new URL('./catalog.json',import.meta.url)));

test('shared links preserve the selected parts and custom colors',()=>{
  const state=normalize({body:'chubby',eyes:'hearts',headwear:'santahat',leftItem:'flower',
    colors:{body:'#BB44CC',bill:'#224466'},hair:false},catalog);
  assert.deepEqual(decode(encode(state),catalog),state);
  assert.equal(state.leftWing,'grab');
});

test('common looks use tiny fragments, with no stored defaults or implied poses',()=>{
  assert.equal(encode(defaults(catalog)),'#v2=');
  assert.equal(encode(normalize({headwear:'crown'},catalog)),'#v2=h4');
  assert.equal(encode(normalize({leftItem:'flower'},catalog)),'#v2=i1');
  const ocean=Object.fromEntries(catalog.colors.map((c,i)=>[c.id,PALETTES[3][1][i]]));
  assert.equal(encode(normalize({headwear:'crown',colors:ocean},catalog)),'#v2=h4.p3');
  assert.equal(encode(normalize({colors:{body:'#aabbcc'}},catalog)),'#v2=Babc');
});

test('all catalog choices, palettes, and custom color overrides round-trip',()=>{
  for(const [key,family] of [['body','bodies'],['eyes','eyes'],['leftWing','wings'],['rightWing','wings'],
    ['bill','bills'],['feet','feet'],['headwear','headwear'],['eyewear','eyewear'],
    ['neckwear','neckwear'],['belly','belly'],['clothing','clothing'],['leftItem','items'],['rightItem','items']]) {
    for(const choice of catalog[family]) {
      const state=normalize({[key]:choice.id,hair:false},catalog);
      assert.deepEqual(decode(encode(state),catalog),state,key+': '+choice.id);
    }
  }
  for(const [,values] of PALETTES) for(const custom of [{},{body:'#112233'},{belly:'#abcdef',feet:'#010203'}]) {
    const colors={...Object.fromEntries(catalog.colors.map((c,i)=>[c.id,values[i]])),...custom};
    const state=normalize({headwear:'santahat',leftItem:'flower',rightItem:'staff',colors},catalog);
    assert.deepEqual(decode(encode(state),catalog),state);
  }
  for(const preset of catalog.presets) {
    const state=normalize(preset.state,catalog);
    assert.deepEqual(decode(encode(state),catalog),state,preset.id);
  }
});

test('existing v1 JSON links still open and can be re-shared as v2',()=>{
  const legacy='#v1=eyJoZWFkd2VhciI6ImNyb3duIiwiZXllcyI6IndpbmsiLCJjb2xvcnMiOnsiYm9keSI6IiNhYWJiY2MifX0';
  const expected=normalize({headwear:'crown',eyes:'wink',colors:{body:'#aabbcc'}},catalog);
  assert.deepEqual(decode(legacy,catalog),expected);
  assert.equal(decode(legacy,catalog).clothing,'none');
  assert.ok(encode(decode(legacy,catalog)).startsWith('#v2='));
  assert.ok(isShareHash(legacy));assert.ok(isShareHash('#v2='));assert.ok(!isShareHash('#something-else'));
});

test('new clothes and objects use compact codes without changing old links',()=>{
  const state=normalize({headwear:'headphone',clothing:'sweater',leftItem:'guitar',rightItem:'laptop'},catalog);
  assert.equal(encode(state),'#v2=hc.i6.j7.c2');
  assert.deepEqual(decode(encode(state),catalog),state);
  const code=tex(state,catalog);
  for(const key of ['headphones','second shirt','guitar left','laptop right']) assert.ok(code.includes(key),key);
  assert.equal(decode('#v2=h4.p3',catalog).clothing,'none');
});

test('v2 links keep their meaning when catalog choices or defaults change',()=>{
  const state=normalize({body:'chubby',headwear:'crown',eyes:'hearts'},catalog);
  const changed=structuredClone(catalog);
  for(const value of Object.values(changed)) if(Array.isArray(value)) value.reverse();
  changed.colors.find(c=>c.id==='body').default='#abcdef';
  assert.deepEqual(decode(encode(state),changed),state);
  assert.deepEqual(decode('#v2=',changed),defaults(catalog));
});

test('new catalog choices can use a literal escape without changing existing codes',()=>{
  const changed=structuredClone(catalog);
  changed.headwear.push({id:'future.hat',label:'Future hat',tex:'future hat'});
  const state=normalize({headwear:'future.hat'},changed);
  assert.equal(encode(state),'#v2=h~future%2Ehat');
  assert.deepEqual(decode(encode(state),changed),state);
});

test('malformed v2 tokens fail without silently changing the penguin',()=>{
  for(const hash of ['#v2=e','7','#v2=hzzz','#v2=pz','#v2=t2','#v2=B12345',
    '#v2=x1','#v2=h1.h4','#v2=h1.','#v2=h~%FF','#v2=h~missing']) {
    assert.throws(()=>decode(hash,catalog),hash);
  }
});

test('links and saved settings only accept catalog values and six-digit colors',()=>{
  const state=normalize({body:'\\input{secret}',eyes:'shiny',headwear:'missing',
    colors:{body:'url(https://example.com)',bill:'#ABCDEF'},hair:'false'},catalog);
  assert.equal(state.body,'normal');assert.equal(state.headwear,'none');
  assert.equal(state.colors.body,defaults(catalog).colors.body);assert.equal(state.colors.bill,'#abcdef');
  assert.equal(state.hair,true);
  assert.throws(()=>decode('#v1='+ 'a'.repeat(5000),catalog));
  assert.throws(()=>decode('#other=123',catalog));
});

test('held items and wing poses stay consistent when either control changes',()=>{
  let state=update(defaults(catalog),'rightItem','lollipop',catalog);
  assert.equal(state.rightWing,'grab');assert.equal(state.rightItem,'lollipop');
  state=update(state,'rightWing','wave',catalog);
  assert.equal(state.rightItem,'none');assert.equal(state.rightWing,'wave');
  assert.equal(state.leftWing,'wave');
});

test('complete document exports include the package and custom color definitions',()=>{
  const state=normalize({colors:{body:'#bb44cc'},headwear:'pumpkinhat',leftItem:'flower'},catalog);
  const code=tex(state,catalog,true);
  assert.ok(code.includes('\\usepackage{tikzpingus}'));
  assert.ok(code.includes('\\definecolor{pinguBody}{HTML}{BB44CC}'));
  assert.ok(code.includes('pumpkin-hat'));assert.ok(code.includes('flower left'));
  assert.ok(!code.includes('script'));
});

test('option formatting needs no percent comments or initial whitespace',()=>{
  const code=tex(defaults(catalog),catalog);
  assert.ok(!code.includes('%'));
  assert.match(code,/\\pingu\[\S/);
});
