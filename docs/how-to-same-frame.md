# 同帧接缝栅格与边界片段就绪性

本切片承接局部重配候选，不改变动画或采用状态。它先补齐边界形状约束所需的可比测量与连续片段证据。

## 同帧、同 ROI、同走廊

比较原 alpha 局部过渡与冲突重配版本。每个 30 FPS 时刻，在两版边界点的共同包围矩形内，用相同的原生像素中心采样；两版对应线段走廊的并集作为唯一统计区域。

分别记录空白／重叠像素、填补的空白、新增空白、增加／减少的重叠，以及两层 alpha 合成覆盖的平均变化。热图选择“新增空白最多，其次候选空白最多”的同一帧，原图、候选图、差分图使用完全相同的矩形和尺寸。

差分图红色为新增空白，绿色为填补，橙色为两版共同空白。该探针仍采用 CPU 双线性 alpha/max 覆盖，不是官方 Runtime 分层 alpha 认证；重叠减少和 alpha 变化本身不被视为通过或失败。

Alice 右侧此前独立走廊的“2 → 1”在共同走廊口径下为“3 → 2”。两个结果方法不同，不能混用或计算统一改善比例。61 个采样时刻均未发现新增空白。其他三处未改变的接缝用于对照。

## 片段就绪性

对参与对应的边界像素建立八邻域图，分离连通分量。仅当分量至少包含三个样本、恰好两个端点且没有分叉时，输出确定性顺序、setup 弧长和归一化 `u`。

孤立点／两点保留为 fragment，分叉或闭环明确标为未就绪。不会把零散采样按坐标强行排序成一条曲线，也不会自动将左右两个分量连接起来。像素邻域图不是精确连续轮廓，斜向接触造成的分叉仍需后续边缘追踪处理。

Alice 腿侧各有两条连续短链；鞋侧存在三点短链和孤立样本，右鞋采样全部为单点／两点片段。因此目前不能直接建立完整 `D(u) ↔ F(u)` 形状约束。这里没有求解切线、曲率或边界长度能量，也没有宣称残余接缝已修复。

## 使用

仓库根目录设置 `PYTHONPATH=src` 后：

```powershell
python -m autospine_workbench.benchmark.same_frame_cli `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --source ../tmp/r2b-seam-remap/alice-v1.json `
  --directory ../tmp/r2b-same-frame/alice `
  --output ../tmp/r2b-same-frame/alice-v1.json
```

另两角色为 lingxian、crino。打开 `index.html` 查看三图对照。报告合同 `autospine.same-frame-seam/v1`，内容地址引用原重配与 alpha 候选。原连续动画和重建的 alpha 动画均核对封存 JSON 字节摘要；reader 重建报告与热图摘要。

所有结果为 `authority:none`、`production_authorized:false`、`needs_review`。没有新生成 Spine 动画，因此本切片不新增官方 Runtime 播放通过声明。已有 4.3.26 导出目标和 4.3.13 Runtime 证据继续各自保留。

下一项：追踪完整的有向 alpha 边缘，为零散目标补充连续曲线上的插值锚点，再在局部区域联合距离、切线与网格面积约束。保留当前同帧栅格探针作为固定验算方式。
