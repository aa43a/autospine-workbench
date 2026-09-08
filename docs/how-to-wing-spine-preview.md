# 从翼根草稿导出 Spine 诊断预览

用户保存的 `wing-root-draft/v1` 可以直接进入导出命令。命令重放来源链并校验完整草稿；不修改原图、旧根部报告或此前正式绑定。

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_spine_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --draft C:/Users/Administrator/Downloads/wing-root-draft-v1.json --output-dir ../tmp/r2b-wing-spine-v2/crino
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-spine-v2 ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

解压 `preview.zip` 后，在 Spine 中导入 `editor/skeleton.json`，保留旁边的 `images` 目录。Runtime 使用包根目录的 JSON、Atlas 和 textures。输出目标为 Spine 4.3.26；本地官方验证器使用外置 spine-webgl 4.3.13，两个版本分别记录。

## 本切片的范围

每个已选主要组件生成一个以真实选择坐标为支点、以 chest 为父级的骨骼。组件使用单骨加权四边形；这用于检验挂接和纹理转换，不代表翼片柔性权重或弹簧物理。两秒循环同时包含胸骨 ±10°、局部 ±12°，正负角按画布 Y 向下到 Spine Y 向上转换。

上衣、翼片与残余共同进入局部包；不是完整角色。低 alpha 边缘与微小组件仍跟随胸骨。上衣包含的翼片投影仍可能重影，层序也尚未复核。因此状态保持 `needs_review`，不产生生产授权。

报告记录源根部、用户草稿、文件内容地址、选择列表、局限和几何结果。合同位于 `schemas/wing-spine-preview-v1.schema.json`；`verify_report` 通过纯导出重放校验整个报告。CLI 将报告及草稿发布到独立内容寻址目录，重复相同输入幂等，已有不同输出拒绝覆盖。

## 验证含义

数值测试覆盖 setup 坐标、父子支点、循环、输入不变、未选项不生成局部骨骼、来源篡改拒绝、报告重放和 schema。Runtime 独立加载官方解析器及渲染器，比较原图参考与 Atlas 的 UV、运动和逐帧像素。

这些验证不判定原始素材重影是否正确。后续已新增 [低 alpha 边缘归属候选与上衣拆分清单](how-to-wing-edge-preview.md)，源层重影仍待语义拆分，再整合完整角色。
