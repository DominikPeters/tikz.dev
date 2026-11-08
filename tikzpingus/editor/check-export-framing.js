// Playwright browser_run_code_unsafe: regression check using real downloads.
async (page) => {
  const context = await page.context().browser().newContext({viewport:{width:1280,height:1000},reducedMotion:'no-preference'});
  try {
    const p = await context.newPage();
    await p.goto('http://127.0.0.1:8767/tikzpingus/#v2=l0');
    await p.waitForSelector('#preview svg.pingu');
    await p.getByRole('tab',{name:'Style',exact:true}).click();
    const choose = async label => {
      await p.getByRole('button',{name:'Headwear: '+label,exact:true}).click();
      await p.waitForFunction(() => document.querySelector('#workspace').getAttribute('aria-busy') === 'false');
    };
    const download = async id => {
      const pending = p.waitForEvent('download');
      await p.locator('#'+id).click();
      const file = await pending, chunks = [];
      for await (const chunk of await file.createReadStream()) chunks.push(chunk);
      return Buffer.concat(chunks);
    };
    const viewport = () => p.locator('#preview svg.pingu:not(.leaving)').getAttribute('viewBox');
    await choose('Bunny ears');
    const earlyViewport = await viewport(), earlySVG = await download('svg');
    await p.waitForTimeout(650); // Allow the 450ms zoom and accessory entrance to finish.
    const settledViewport = await viewport(), settledSVG = await download('svg');
    if (earlyViewport === settledViewport) throw new Error('The test did not exercise the zoom transition.');
    if (!earlySVG.equals(settledSVG)) throw new Error('SVG export changed with preview animation timing.');
    await choose('None'); await p.waitForTimeout(650);
    await choose('Bunny ears');
    const earlyPNG = await download('png');
    await p.waitForTimeout(650);
    const settledPNG = await download('png');
    if (!earlyPNG.equals(settledPNG)) throw new Error('PNG export changed with preview animation timing.');
    return {svgIdentical:true,pngIdentical:true,earlyViewport,settledViewport,
      exportedViewport:earlySVG.toString().match(/viewBox="([^"]+)"/)[1],
      pngSize:[earlyPNG.readUInt32BE(16),earlyPNG.readUInt32BE(20)]};
  } finally {await context.close();}
}
