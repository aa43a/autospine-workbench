// Surface module-load errors instead of leaving a permanently empty review page.
export async function startCohort(load, status) {
  try { await load(); return true; }
  catch (error) {
    status.textContent='动作复核界面未能加载，请刷新页面重试。错误：'+String(error?.message||error);
    return false;
  }
}
if (typeof document !== 'undefined') {
  await startCohort(()=>import('./motion-cohort.js'),document.getElementById('status'));
}
