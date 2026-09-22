# M4 deform 文本压缩：官方 Runtime 数据与画面保持一致

2026-09-22。存储优化验证通过；不是 Reach 遮挡或视觉接受结论。

## 原因与实现

未合并普通裁剪候选的 scene 为 51,880,886 字节，其中 skeleton 约 49.3 MB，主体是 deform 数值文本。直接删帧或近似合并几何不适合当前未收敛的遮挡候选。

新增 `targets/spine43/deform_storage.py`，只缩短 deform 关键帧 vertices 内的数字文本。保留原数值读入 Float32 后的精确位模式，不改变关键帧数量、时间、曲线、offset、setup vertices、UV、骨骼与材质。非有限值及 Float32 溢出拒绝，负零保留。依照已检查的官方 SkeletonJson：deform 首先进入 Float32 数组，之后才做缩放及 unweighted setup 加法。

该语义绑定于已验证的 typed-array Runtime，不声称对任意双精度第三方解析器完全等价。原源文档保留，生成新候选及明确压缩 profile；没有覆盖历史身份。

## 验证

- 官方 spine-core 4.3.13 解析压缩前后两个完整 skeleton：119,536 个 deform 关键帧、2,346,376 个数值逐位相同；帧时间和曲线一致；原 JSON 中除 deform 数值外所有字段一致。
- 官方 WebGL Runtime 对比隔离的完整手臂，241 个键时刻及其中点，共 481 个时刻：所有预乘 RGBA 像素完全相同，最大差异 0。
- 删除手臂的负对照能检测到缺失；从末尾回退起点完全复现。
- 同步播放器的身份、播放暂停、时间轴和回退检查通过。
- 20 个相关单元测试通过，包含随机 Float32 位等价、极小数、符号零、溢出拒绝、非 deform 字段保持，以及现有裁剪和加权压缩回归。

scene 从 **51,880,886 降至 31,490,688 字节**，减少约 **39.3%**。手臂仍为 477 个槽位；没有借文件压缩宣称降低绘制复杂度，也没有以测试总耗时充当实际播放帧率。

## 身份和输出

- 原连续候选：`971b6206f3eec435e1d0767bdc4ea1fbce3b0e16ddfef0ab40c237aae9e77c78`
- 压缩后候选：`4f29c78193027ec43200b098aed62157549c946419cc95c07a25cbf86e7e968f`
- 共同角色动作父候选：`21969ed99dd41e85171f52842fc4754a8d8c4bd425fd722cf87a78ce94b9d437`
- localset 下 `tmp/m4-motion-center/reach-storage-clips-v1/storage-check.json`：官方解析位等价证明。
- 同目录 `comparison-equivalent/report.json`：Runtime、输入场、scene 摘要及实际像素对照。
- 同目录 `player-check/check.json`：同步播放器检查。

目标 Spine 4.3.26，当前捕获 Runtime 4.3.13，版本分别记录。压缩候选仍未默认采用；未合并候选已有的单像素重构差异和肩部外观问题仍存在，不被本次等价验证抵消。

下一切片回到动作表达：对压缩候选检查前后边界插值与肩部连接材料。停止近似几何合并的重复调参，不再把主要工作转成存储优化。
