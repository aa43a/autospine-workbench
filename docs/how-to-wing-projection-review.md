# 主翼反向投影分组复核

本切片在用户已有 11 笔拆分后的上衣纹理上生成四组候选。对每片主翼，将 alpha>=8 的像素按原画布偏移投回上衣，并仅保留当前上衣 alpha>0 的交集。候选使用行区间 `[y, x_begin, x_end)` 保存，没有矩形填充、膨胀、RGB 相似性推断或遮挡补全。

这是疑似重复区域，不是像素所有权的证明。投影只覆盖当前翼片 alpha 支持的范围；上衣中更宽的描边、内部底色或其他残留可能不在候选内，不能把选择四组移除等同于重影已解决。

## 使用

每组可选择“移除候选／保留／不确定”，默认全部不确定。左侧黄色为投影候选，红色为拟移除；右侧可切换翼片参考，观察静态合成。局部笔刷支持待移除、明确保留和恢复分组结果；局部笔画优先于分组。多个分组覆盖同一点时，只要有保留或不确定就默认保留。

已有 11 笔清理对应的上衣净层是本轮底图，重置只撤销本轮操作。局部“保留”不会恢复上一步已移除的素材。需要回退此前清理时使用原拆分草稿，而不是混用本轮选择。

保存完整 `wing-projection-draft-v1.json`，提交后可校验本轮分组及局部修正，再生成下一版候选。当前页面不改原图、不生成新的正式 Spine 包，不产生生产授权。

## 合同与验证

候选 `wing-projection-groups/v1` 绑定已应用拆分报告、原上传草稿和当前上衣纹理身份；草稿 `wing-projection-draft/v1` 绑定精确候选及原上传草稿。`read_candidate` 重放投影并校验源文件，`validate` 严格检查组顺序、动作、来源与局部笔画预算；`effective_mask` 纯函数组合分组和局部笔画。原像素源及旧合同不改变。

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_projection_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-split-applied/crino/preview-manifest.json --html ../tmp/r2b-wing-projection/crino/review.html --output ../tmp/r2b-wing-projection/crino/groups.json --draft-output ../tmp/r2b-wing-projection/crino/draft.json
node tools/check-wing-projection.mjs ../tmp/r2b-wing-projection/crino ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe'
```

恢复保存草稿时传 `--draft` 并选择新的输出路径。琪露诺四组分别为 5,627、4,905、4,046、2,983 像素。7 项针对性测试通过；浏览器检查逐组选择、局部保留覆盖、撤销、下载、恢复和错误来源拒绝。测试选择未发布；交付为全部不确定、0 笔局部修正。本切片没有新的官方 Runtime 运行。
