# 从保留残余提取独立挂坠

本切片消费主翼颜色恢复后的 `color/unassigned.png`。四个挂坠分别生成裁剪纹理、顶部 pivot 和主翼子骨骼，进入局部 Spine 播放候选。此前人工删除的其他像素不会被恢复。

## 提取与挂接

`residual-crystal-unique-tip-v1` 从 alpha>=8 且有颜色或较暗的像素提取四邻接连通域，要求至少256个种子像素、高宽比至少1.2。封闭区域内的高光保留原 RGBA；不对外扩张。多个区域争用的像素仍留在残余中。所有提取图与残余必须精确重建输入的 alpha 和非透明 RGBA。

顶部一行的中位位置作为 pivot。将其与主翼 alpha 轮廓比较，最近距离不超过8px、与第二候选距离差至少8px才生成挂接候选。距离或歧义不满足条件时保留提取图并阻塞挂接。这是晶体形状启发式，不是通用语义识别，也不产生人工批准。

挂坠使用单骨加权四边形，骨骼作为对应主翼的子骨骼。局部 ±6° 两秒循环用于检查顶部挂接与层序，不代表物理模拟。新 slot 位于上衣之前，原附件的相对顺序不变；编译时逐一比较原六个附件在121个采样时刻的世界坐标。

## 复现

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_pendant_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-color/crino/preview-manifest.json --output-dir ../tmp/r2b-wing-pendants/crino
python -m unittest tests.test_wing_pendants tests.test_wing_color_ownership tests.test_quality -q
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-pendants ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

CLI 验证源报告的内容地址和文件清单，重复输出要求字节相同。输出 `preview.zip`、`review.html`、`pendants/candidates.json`、四个独立 PNG 及 `pendants/residual.png`。ZIP 的编辑器文件与图片目录需一起保留。

## 2026-09-09 结果

四个挂坠共13,275个可见像素，残余从14,658降到1,383。两侧各两个挂坠挂接到对应上翼，四个顶部距翼轮廓均为1px。9项针对性测试通过，原六个附件的121帧坐标完全一致。

导出目标 Spine 4.3.26，验证使用外置官方 spine-webgl 4.3.13。121帧 Runtime 检查通过，Atlas 与独立原图参考的最大通道误差为0。检查摆动截图，挂坠随主翼运动并绕顶部摆动。

这是局部候选，仍为 `needs_review` / `authority: none`，不是完整角色验收。下一步将主翼、挂坠和清理后的服装接入完整角色，验证层序及源图层消费覆盖；剩余边缘像素继续独立保留。
