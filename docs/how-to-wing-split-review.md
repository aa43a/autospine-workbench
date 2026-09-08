# 上衣／翼片拆分遮罩编辑

本页消费已校验的翼片边缘预览包。它让用户直接在上衣源图上连续涂抹，保存与精确源报告及纹理 SHA 绑定的草稿。初始草稿为空；重叠 bbox 仅作黄色提示，不会预填移除区域。

## 标注

1. 左侧选择“待移除”，涂出上衣源图中的翼片投影。
2. 用“明确保留”标记衣领、肩部、蝴蝶结等真实服装；绿色只表示当前标注状态，后续笔画可以覆盖它。
3. “擦除标注”恢复未标注状态。未标注像素在预览中保留。
4. 右侧可切换翼片参考，检查移除上衣投影后的组合。两侧均支持缩放和滚动。
5. 保存完整 `wing-split-draft-v1.json`；提交该文件后，再校验并生成新的拆分候选。

支持撤销／重做、重置撤销及来源校验后的草稿恢复。不会修改原图、当前 Spine 包或根部决定。右侧只是浏览器静态预览，不是官方 Runtime 验证，也不产生生产授权。

## 合同与实现

`autospine.wing-split-draft/v1` 使用 `integer-disc-tristate-v1`：目标纹理局部整数坐标，半径 1–64，0 未标注、1 待移除、2 明确保留。沿笔画按最大坐标差插值，使用 floor(value+0.5) 舍入，整数圆覆盖。后写笔画覆盖之前状态。

最多 500 笔、4096 个路径点、800 万画布像素。JSON Schema 限制形状，语义 validator 检查总量、坐标范围、数值类型和来源；JS 与 Python 栅格结果逐字节测试一致。非法半径、NaN、越界坐标、错误来源及伪造授权均拒绝。

页面嵌入按内容地址验证的图片，可离线使用。CLI 从不可变源报告与文件清单读取素材；保存到内容寻址 store 的仍是草稿，reader 再验证源报告和草稿身份。本切片没有源层修改或新的正式 Runtime 导出。

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_split_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-edges/crino/preview-manifest.json --html ../tmp/r2b-wing-split/crino/review-v3.html --draft-output ../tmp/r2b-wing-split/crino/draft.json
node tools/check-wing-split.mjs ../tmp/r2b-wing-split/crino ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' review-v3.html
```

恢复已保存标注时传入 `--draft` 并使用新的输出路径，以保留原版本。

8 项针对性测试通过。浏览器验证实际拖动画笔、保留、擦除、撤销／重做、重置撤销、缩放、完整下载、恢复及错误来源拒绝。测试笔画未写入交付草稿，交付为 0 笔。下一步等待用户的实际遮罩草稿，生成不覆盖原始纹理的拆分候选，并复跑同动作 Runtime 对照。
