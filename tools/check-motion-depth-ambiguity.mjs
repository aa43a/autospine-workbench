import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const module=await readFile(new URL('../web/modules/motion-local-depth-details.js',import.meta.url),'utf8');
const locationModule=await readFile(new URL('../web/modules/motion-depth-location.js',import.meta.url),'utf8');
const browser=await chromium.launch({channel:'chrome',headless:true});
try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('http://depth.test/**',route=>{
    const path=new URL(route.request().url()).pathname;
    if(path==='/module.js')return route.fulfill({contentType:'text/javascript',body:module});
    if(path==='/motion-depth-location.js')return route.fulfill({contentType:'text/javascript',body:locationModule});
    if(path==='/local-depth-status.json')return route.fulfill({json:{artifact_sha256:'a',reports:[{
      spatial_sampling:'barycentric_pixel_intervals',interpolation:'linear_observed_positions',
      requested_sample_times:[0,1.5,3],
      sleeve_helpers:{cloth:'forearm_l'},
      causes:{pairs:[{pair:['arm','body'],reasons:{depth_margin_ambiguity:1},
        ambiguity_causes:{near_plane_back:41,interval_crosses_plane:0}}]},
      records:[{pair:['arm','body'],time:1.5,unavailable_helpers:{cloth:'sleeve_plane_projected_axes_degenerate'}}],records_truncated:false}]}});
    return route.fulfill({contentType:'text/html',body:`<main></main><script type="module">
      import {appendLocalDepthDetails} from '/module.js';
      appendLocalDepthDetails(document.querySelector('main'),{result:{artifact_sha256:'a'}},'/');
      </script>`});
  });
  await page.goto('http://depth.test/');
  await page.getByRole('button',{name:'查看局部深度补充检查'}).click();
  await page.getByText('逐像素检查 · 帧间插值模型 · 服装平面假设',{exact:true}).click();
  const text=await page.locator('main').innerText();
  assert.ok(text.includes('靠近躯干后侧，间隔不足 41'));
  assert.ok(text.includes('仍未通过前后关系验收'));
  assert.ok(text.includes('限定 3 个时刻的补充检查，不覆盖整段'));
  assert.ok(text.includes('原完整检查中的失败和未测记录继续保留'));
  assert.ok(text.includes('不代表观测到真实布料深度'));
  assert.ok(text.includes('cloth → forearm_l'));
  assert.ok(text.includes('前臂投影接近竖直，无法确定平面'));
  assert.ok(text.includes('全映射诊断'));
  assert.ok(!text.includes('深度区间跨越躯干平面 0'));
  assert.equal(await page.getByRole('link',{name:'定位 1.500 秒'}).getAttribute('href'),'/player.html?time=1.5&mode=isolate&region=arm&region=body');
  assert.deepEqual(errors,[]);console.log(JSON.stringify({passed:true}));
}finally{await browser.close();}
