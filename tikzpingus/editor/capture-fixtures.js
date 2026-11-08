// Run with Playwright browser_run_code_unsafe on the built editor, then save
// window.editorFixtures with browser_evaluate to feed verify.py.
async (page) => {
  await page.reload();
  await page.waitForSelector('#preview svg');
  return await page.evaluate(async () => {
    const appURL=document.querySelector('script[type=module]').src;
    const app=await(await fetch(appURL)).text();
    const core=await import(new URL(app.match(/from '\.\/([^']+)'/)[1],appURL));
    const catalog=await(await fetch(new URL(app.match(/'\.\/(catalog\.[^']+)'/)[1],appURL))).json();
    const packs={};
    for(const [id,path] of Object.entries(catalog.packs)) {
      packs[id]=core.parsePack(await(await fetch(new URL(path,appURL))).text());
    }
    const fixtures=[];
    const add=(name,input) => {
      const state=core.normalize({eyes:'normal',leftWing:'normal',rightWing:'normal',...input},catalog);
      fixtures.push({name,state,tex:core.tex(state,catalog),
        svg:core.serialize(core.compose(packs[state.body],state,catalog,'fixture-'))});
    };
    for(const body of catalog.bodies) {
      add(body.id+'/base',{body:body.id});
      for(const [family,key] of [['eyes','eyes'],['wings','leftWing'],['wings','rightWing'],
        ['bills','bill'],['feet','feet'],['headwear','headwear'],['eyewear','eyewear'],
        ['neckwear','neckwear'],['belly','belly'],['clothing','clothing']]) {
        for(const choice of catalog[family]) {
          const label=family==='wings'?key:family;
          add(body.id+'/'+label+'/'+choice.id,{body:body.id,[key]:choice.id});
        }
      }
      for(const side of ['left','right']) for(const choice of catalog.items) {
        add(body.id+'/'+side+'Item/'+choice.id,{body:body.id,[side+'Item']:choice.id});
      }
      add(body.id+'/mixed',{body:body.id,eyes:'shiny',leftWing:'wave',rightWing:'grab',
        headwear:'hat',eyewear:'glassesround',neckwear:'scarf',belly:'cup'});
      add(body.id+'/colors',{body:body.id,eyes:'hearts',leftItem:'flower',rightItem:'lollipop',
        headwear:'santahat',colors:{body:'#123456',belly:'#c7d9e9',eyes:'#8e174f',bill:'#f17654',feet:'#799e1a'}});
      add(body.id+'/bald',{body:body.id,hair:false,eyes:'critical',leftWing:'shock',rightWing:'hug',headwear:'crown'});
      for(const preset of catalog.presets) add(body.id+'/preset/'+preset.id,{...preset.state,body:body.id});
      for(const clothing of catalog.clothing.filter(c=>c.id!=='none')) {
        add(body.id+'/clothes-mixed/'+clothing.id,{body:body.id,clothing:clothing.id,eyes:'shiny',
          headwear:'headphone',neckwear:'scarf',belly:'cup',leftWing:'wave',rightWing:'grab'});
        add(body.id+'/clothes-colors/'+clothing.id,{body:body.id,clothing:clothing.id,leftItem:'laptop',rightItem:'microphone',
          colors:{body:'#75405b',belly:'#fff1e8',eyes:'#332233',bill:'#efa56e',feet:'#efa56e'}});
      }
    }
    window.editorFixtures=fixtures;
    return {cases:fixtures.length};
  });
}
