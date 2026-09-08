# 先纠正翼片层序，再判断源层残留

用户明确要求主翼位于其他图层后方。本切片修正当前翼片／上衣局部包的 setup slot 次序，把四个主翼组件及翼片残余整体放到上衣之前（Spine 由后至前绘制），保持翼片内部次序。

原次序：topwear → wing-residual → wing-c0 → wing-c1 → wing-c2 → wing-c3。

新次序：wing-residual → wing-c0 → wing-c1 → wing-c2 → wing-c3 → topwear。

仅修改 Runtime 和 Editor 两个 skeleton JSON 的 slots 数组顺序。所有纹理、Atlas、UV、骨骼、根部、动画和此前用户11笔清理不变；不采用尚未提交的主翼投影删除草稿。若动画已有 drawOrder 轨道则拒绝本简单重排，避免播放时覆盖 setup 修正。

当前只有6附件的局部包，因此“置于所有其他附件后方”在本次意味着置于上衣后方，不代表完整角色18层已接入或层序验收完成。

## 运行

```powershell
$env:PYTHONPATH=(Resolve-Path ./src).Path
python -m autospine_workbench.benchmark.wing_back_order_cli --manifest docs/benchmark/manifest-frozen-v1.json --source ../tmp/r2b-wing-split-applied/crino/preview-manifest.json --output-dir ../tmp/r2b-wing-back-order/crino
node tools/verify-ownership-runtime.mjs ../tmp/r2b-wing-back-order ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' crino
```

同帧比较器增加显式 `--slot-order-only` 模式：仅在按名称规范化 slots 后的完整 skeleton 相同、Runtime 相同时允许对照。普通模式继续要求 skeleton 字节身份相同。

```powershell
node tools/compare-wing-edge-runtime.mjs 'http://127.0.0.1:1744/?character=crino' 'http://127.0.0.1:1622/?character=crino' ../tmp/r2b-wing-back-order/comparison ../tmp/spine43-verification 'C:/Program Files/Google/Chrome/Application/chrome.exe' --slot-order-only
```

## 结果

5项针对性测试与官方 Runtime 121帧通过。输出目标4.3.26，外置官方 spine-webgl 4.3.13。Atlas 与本候选原图参考最大通道差为0。

原层序／后置层序的 setup 有7,303个像素变化，0.5秒有4,111个，1.5秒有4,068个，最大通道差131。五个采样帧均无 alpha8 可见像素损失。颜色变化是不同图层遮挡次序的结果，不是权重变化。

查看0.5秒截图后，静态翼片轮廓仍存在；上衣源图内的翼片位于运动翼片前方，继续造成遮挡与重影。因此此前诊断预览的层序确实需要纠正，但修正层序不能代替源像素归属处理。

下一项基于后置层序继续复核上衣翼片残留；保持独立运动翼片，不通过重绑或调权重掩盖源图问题。当前仍为诊断候选，无生产授权。
