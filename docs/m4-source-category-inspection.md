# 固定动作来源内容检查

已从八个经过哈希校验的源预览生成正面、侧面六时刻骨架图，并逐图检查。
图集：`../tmp/m4-motion-center/source-category-sheets-v1/index.html`。
对应来源、预览和图片摘要见
[观察记录](benchmark/m4-source-category-observations-v1.json)。

| 固定动作 ID | 实际采样内容 | 范围限制 |
| --- | --- | --- |
| breathing | 站立、手臂下垂、姿态变化较小 | 待机样本；六帧不能证明呼吸周期 |
| walking | 交替迈步，手臂明显前伸并屈肘 | 特定风格行走，不能代表所有自然摆臂 |
| raise-arms | 右臂在身前屈肘抬动 | 单臂欢呼，不是双臂完整举过头顶 |
| turn | 屈膝时躯干和双肩方向改变 | 转向样本，不能宣称覆盖完整 360° |
| squat | 双臂高举，骨盆下降、屈膝后恢复 | 高举双臂下蹲这一组合 |
| boxing | 手臂交替屈伸、躯干倾斜 | 与出拳标签相符，不判断拳法或接触时刻 |
| reach | 右手从身旁向前上方伸出 | 单侧前伸，不是任意方向抓取 |
| wave | 左臂抬起，手和前臂朝向变化后回落 | 与左手挥手提示相符，不证明全部中间帧 |

这些是助手对真实采样姿态的观察，不是人工阶段验收、动作分类 Ground Truth，
也没有改写冻结计划。原始文件名/提示标签与实际观察分别保留。固定矩阵的
覆盖描述应限定到这些具体动作，不能把它们扩大为每个动作大类都受支持。

生成工具按整个源预览计算同一视角的画布边界，避免逐帧缩放制造假动作。
每图两行分别使用原始世界关节的 (+X,-Y) 与 (-Z,-Y) 投影；橙色为左侧，
蓝色为右侧。两个投影不改变原动作，不产生新的角色候选或侧面素材。

```powershell
$env:PYTHONPATH='src;tools'
python tools/m4_source_motion_sheets.py docs/benchmark/m4-cohort-plan-v3.json ../tmp/m4-motion-center/cohort-diagnostics-refreshed-v1.json ../tmp/m4-motion-center/source-category-sheets-v1
```

输出必须是新目录。工具核对计划、源文件和预览身份后才生成图，保留选中
源帧编号和图片摘要。六时刻概览用于内容检查；连续动作仍在工作台源时间轴查看。
