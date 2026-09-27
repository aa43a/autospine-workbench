// Six-pose observations recorded in docs/benchmark/m4-source-category-observations-v1.json.
// Exact source identity only; these descriptions never establish visual acceptance.
const plan='289d24b4dd1d70d539265bb26c18ffa06b3d11e17173389ac87dbacb1886b940';
const records={
  breathing:['67bf8b91cb77fec8873bb059cddcb96198c9ca348a16cfa6eb60171dabbd5370','站立、手臂下垂，姿态变化较小。','六个采样不能证明呼吸周期或胸部起伏。'],
  walking:['ba4923f188ee8580dbe07f79191c154cbad0425ba71a74229eeeba40ea015a68','交替迈步，双臂明显前伸并屈肘。','特定风格行走，不代表所有自然摆臂行走。'],
  'raise-arms':['779dcb5c003f715905f48eafaea706c4ab524d97c7554f6b90c178bff5eecdc9','右臂在躯干前屈肘抬动，左臂大致下垂。','单臂欢呼／屈肘抬臂，不是双臂完整举过头顶。'],
  turn:['543bfe46e10c5bf921e5fd16473340afe3563a6c18c2b7bb7bf9ed027c8ef165','屈膝时躯干和双肩方向改变。','不证明完整 360° 转身受支持。'],
  squat:['596014069e4ecc8527ba37feded9d7b8564d50832862dad89c0a75ca7c136bba','双臂高举，骨盆下降、屈膝后恢复。','高举双臂下蹲，不代表所有下蹲深度或手臂组合。'],
  boxing:['9bbfe8fc1adf850fbf849a85d308d62f80394f81ee7eb3f483cd68cc6fd80d69','双手交替屈伸，伴随躯干倾斜和步态变化。','采样不用于判定拳法或接触时刻。'],
  reach:['89e7b2785bdb93d4c1506d3621701126e37f47acb8757a6e76bde6eed3fbe615','右手从身旁逐渐向前上方伸出。','单侧前伸，不代表任意方向双手抓取。'],
  wave:['2ee03d7638686150305d61ff6bd5d8f21a05693cf139bb20467017feb3d363a6','左臂抬起，手与前臂改变朝向，最后回落。','六个采样不证明完整频率、连续性或全部中间姿态。'],
};
export function sourceScope(planHash,row){
  const r=records[row.motion];
  if(planHash!==plan||!r||row.source_sha256!==r[0])return null;
  return {observed:r[1],limits:r[2],authority:'none',observer:'assistant_visual_inspection',
    scope:'six_sample_poses_not_continuous_motion_or_human_acceptance'};
}
