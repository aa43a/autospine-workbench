// The fixed baseline is navigation only. Live jobs and evidence are verified by the page.
export async function navigationPack(hash, search, get) {
  if (hash) {
    if (hash.length > 100000) throw Error('复核清单过大');
    return JSON.parse(decodeURIComponent(hash.slice(1)));
  }
  const packs=new Map([['m4-fixed','/m4-fixed-cohort.json'],
    ['m4-reach-shared45','/m4-reach-shared45-cohort.json']]);
  const path=packs.get(new URLSearchParams(search).get('pack'));
  if(!path)throw Error('未选择固定复核清单');
  return get(path);
}
