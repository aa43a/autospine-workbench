// The fixed baseline is navigation only. Live jobs and evidence are verified by the page.
export async function navigationPack(hash, search, get) {
  if (hash) {
    if (hash.length > 100000) throw Error('复核清单过大');
    return JSON.parse(decodeURIComponent(hash.slice(1)));
  }
  if (new URLSearchParams(search).get('pack') !== 'm4-fixed')
    throw Error('未选择固定复核清单');
  return get('/m4-fixed-cohort.json');
}
