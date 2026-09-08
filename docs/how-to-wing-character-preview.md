# 在完整角色中检查主翼与挂坠

这一入口把已生成的主翼、挂坠及清理后的上衣放回全部源图层中，输出可直接导入 Spine 的完整画面。它用于检查遮挡、重复像素和图层遗漏，不是新增身体绑定决定。

## 合成约束

源层通过翼根报告的内容地址重放，验证角色身份、图层清单、图像 SHA 和尺寸。翼片包的文件清单也必须逐项一致。原始翼层与原始上衣不会作为整层再次叠入，否则会重新引入已经处理的重复像素。

其余图层在原画布坐标下生成单骨四边形，仅作为跟随胸部的刚性参照。翼片与挂坠组排在所有身体图层之前；其余身体图层保留源顺序。旧骨骼、轨道、纹理和附件不改，121个时刻的原附件世界坐标必须逐值相同，新附件在 setup 下必须重建源 bbox。

`autospine.wing-character-preview/v1` 记录每个源图层的当前表示。`rigid_context_only` 不等同于已确认绑定；图层均有表示也不等于全部像素已采用。颜色转移、挂坠及残余原始证据保留在包内，未归属残余不会被强行显示。

## 运行

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_character_cli --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. --source ../tmp/r2b-wing-pendants/crino/preview-manifest.json --output-dir ../tmp/r2b-wing-character/crino
python -m unittest tests.test_wing_character_preview tests.test_wing_pendants tests.test_quality -q
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-character ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

输出包括 `preview.zip`、`review.html` 和 `context/coverage.json`。解压 ZIP 后导入 `editor/skeleton.json`，保持 `images` 目录相对位置。新报告在 `wing-character-previews-v1` 中内容寻址发布；已有输出不同时拒绝覆盖。纯 reader `verify` 可重放全部文件与报告。

## 2026-09-09 结果与范围

- 琪露诺18个源层均列入清单：原10个候选附件，加16个刚性身体参照，共26个附件。
- 1,383个未归属像素继续保留。没有修改或重新采用此前人工删除的像素。
- 9项针对性测试通过，覆盖来源变更拒绝、setup坐标、源层顺序、旧动作不变、重放和文件清单；文件长度检查通过。
- 导出目标 Spine 4.3.26，实际外置官方 Runtime 为 spine-webgl 4.3.13。121帧通过，最大 setup 误差0.0000611px、运动误差0.0000875px、Atlas与独立原图参考的最大通道差0，画布溢出0。
- 查看 setup 与0.5秒摆动截图，主翼和挂坠位于身体、头发及服装之后，未见此前明显的静态主翼副本。截图检查不能替代所有动作的重影和接缝门禁。

当前 `full_character_animation: false`，`authority: none`。身体是整块参照，没有合入独立四肢动作、头发或裙摆物理。下一步需要把已选翼根与挂坠转换到角色 canonical skeleton，再与既有四肢候选合并；不能直接拼接两个不同骨架或把参照层当成正式刚性绑定。
