# 无损组件分区预览

`partition-layer-candidates` 消费可重放的结构候选，输出逐像素左右分区及待定残余。
仅接受恰好两个主要连通域、侧别分别为 l/r 的分区候选；不会为服装或未知物件强行切图。

```powershell
python -m autospine_workbench.benchmark partition-layer-candidates `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --structure ../tmp/r2b-structure/alice-v1.json `
  --zip ../tmp/r2b-partitions/alice-v1.zip `
  --html ../tmp/r2b-partitions/alice-v1.html `
  --output ../tmp/r2b-partitions/alice-v1.json
```

每层 ZIP 目录包含 source.png、left.png、right.png、residual.png、ownership.png。
它们保留原图尺寸，报告 bbox 给出 PSD 画布偏移。ownership 是 L 模式分类掩码，
像素值 1/2/3 表示角色左侧、右侧、残余；不是适合肉眼直接查看的灰度图。
HTML 展示三部分，并提供残余像素诊断高亮，诊断色不属于导出素材。

## 归属与无损定义

主组件保持上一阶段的组件身份和侧别，并重新校验面积、bbox、重心。
alpha≥8 的小组件整体按到两个主组件重心的距离归属，距离差不超过 1px 时留在残余。
alpha 1–7 的边缘从已分配组件沿低 alpha 像素进行四连通最短距离传播；等距与孤立像素留在残余。
alpha=0 的像素连同其 RGB 字节保存在 residual 中。不会删除噪点或丢弃透明 RGB。

三个输出互斥拥有源像素；逐通道合并后，RGBA 字节和摘要必须与解码后的 source.png 一致。
这不是 PNG 编码字节相同的声明。ZIP 另保留原始 PNG，且报告记录所有导出文件的 SHA256。
manifest 不含自身或 ZIP 摘要，外部回执附 ZIP 摘要，避免自引用。
`read_partitions` 重新读取结构及其来源，重新分区并重建 ZIP 后验证回执。

## 实际结果与限制

三个开发角色共六层已生成候选。六层 RGBA 与 ownership 独立重建检查通过，
Alice 的完整分区 reader 重放通过；16 项相关测试通过。未运行全量测试或官方 Runtime。
详细像素与 alpha 总量见 [验证记录](benchmark/layer-partitions-2026-09-08.json)。

无损不等于侧别正确，也不等于所有像素已经完成归属：铃仙腿部仍有 30,893 个低 alpha 残余像素。
这些像素的可见贡献需要结合 alpha 总量和高亮检查，不能仅按像素数量判断视觉影响。
所有分区保持 needs_review，既有绑定、Mesh/Bake 和 Spine 包均不改写。

下一步处理残余归属复核与分区采用合同，然后把分区身份接入多区域 Mesh/Weight，
验证双腿与脚踝动作。不能直接忽略 residual 导出两张图片并宣称完整角色已重建。
