# 将翼根、挂坠与四肢接入同一标准骨架

在上一版完整角色上下文基础上，使用与同一角色语义工件对应的 canonical skeleton，接入既有双臂、双腿、双脚分区候选。原局部诊断骨架不再作为第二套骨架叠加。

## 坐标与动作

`wing_rebase` 将原翼片及挂坠的 setup 世界坐标转换为标准骨架的父级局部坐标，重新计算骨索引和加权顶点局部坐标。主翼骨挂在标准 chest 下，挂坠仍挂在对应主翼骨下。标准骨架原骨骼保持原顺序和参数。

旧预览的胸部 ±10° 整身摆动被明确移除。保留翼片、挂坠自身的局部旋转；以移除该胸部轨道的旧包为参照，121帧位置误差必须小于1e-7px。不能将这个指标描述为“完整旧预览动作不变”。

四肢原骨骼轨道、附件、权重、deform 和纹理直接保留，合并后121帧世界坐标逐值相同。不同片长、骨名冲突和共享动作轨道冲突拒绝合并。当前转换只处理既有旋转轨道与加权 Mesh，不支持额外约束、缩放或切变。

## 图层与残余

分区所属源层由内容寻址 ownership atlas 提供，不从附件名字猜测。对应 Atlas 页 SHA 必须与四肢包中的纹理相同，标准骨架也必须与从标注链重放出的骨架完全一致。

手臂、腿和鞋的整层参照替换为两个分区附件及一张独立残余参照。残余从已有 Atlas 的 owner=3 tile 精确裁出，保留颜色、透明度和原画布偏移，不做最近邻填充，也不自动确认其绑定。主翼与挂坠仍在所有身体图层之后，其余源层顺序及四肢相对顺序保留。

## 复现

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_limb_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --source ../tmp/r2b-wing-character/crino/preview-manifest.json --limbs ../tmp/r2b-stable-fallback/crino/ea482f812a1c6650170baadb4260b4165357e2890a4b9c6ef81dd1855c97939b.json --ownership ../tmp/r2b-isolation/crino-v1.json --output-dir ../tmp/r2b-wing-limbs/crino
python -m unittest tests.test_wing_limb_preview tests.test_wing_character_preview tests.test_quality -q
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-limbs ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

输出 `preview.zip`、`review.html`、`context/coverage.json` 和 `limb-residual/*.png`。报告发布到 `wing-limb-previews-v1`，绑定原上下文、四肢、ownership 和骨架地址；纯 reader `verify` 可重放报告与字节清单，不覆盖内容不同的历史输出。

## 2026-09-09 结果

- 琪露诺28骨骼、32附件，含6个四肢分区及4片主翼、4个挂坠。
- 换骨架后的翼片局部动作误差最大5.69e-14px；四肢原动作121帧逐值一致。
- 四肢残余12,361像素仍仅作刚性参照：手臂8,188、腿3,709、鞋464。另保留翼片未归属1,383像素。
- 10项针对性测试通过，覆盖旋转父坐标、来源与ownership变更拒绝、残余替换、旧动作不变、重放、Schema及文件长度检查。
- Spine导出目标4.3.26，官方外置spine-webgl 4.3.13的121帧检查通过。最大setup误差0.0000763px、运动误差0.0001131px；Atlas与独立原图参考最大通道差1，没有大于1的通道误差，画布溢出0。
- 查看0.5秒弯曲截图，翼片、挂坠与四肢可同时运动，未见原整层手臂／腿鞋参照导致的明显重复。

这不是完整角色生产验收：保留 `full_character_animation: false` 和 `authority: none`。未批准的身体图层仍为刚性参照，袖口与肩部接触、裙摆遮挡、残余归属和其他动作仍待复核。下一步应集中检查这些新出现的跨部件视觉关系，不重新调节已保持一致的腿鞋轨道，也不把待复核残余静默标为完成。
