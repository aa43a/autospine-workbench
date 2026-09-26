# 外部动作的 Runtime 数值参考

官方 Spine 4.3.13 将关键帧时间、旋转/平移/缩放值、变形关键帧数组及加权 Mesh 局部坐标和权重存为 Float32。骨骼 setup 属性仍为 JavaScript Number。理想双精度 FK 与实际存储后的 FK 在高梯度动作处可能相差超过 0.001 px。

`spine43-linear-weighted-float32-storage-v1` 独立模拟这些输入数组的存储精度，再计算同一时刻的顶点。不改写导出的 skeleton、权重、纹理或动画。几何门禁仍读取原始理想参考；Runtime 对照使用独立存储参考，仍执行原有 0.001 px 门槛。

捕获报告同时保存参考文件哈希、实现哈希、理想与存储结果的最大位移。捕获器核对 skeleton 身份、完整动画/时刻/附件/顶点清单和实际最大位移。两份参考共同决定截图范围，避免遗漏任一边界。未知曲线、非支持附件或 Float32 下合并的关键帧时间会明确失败，不猜测其语义。

新提交的外部动作请求写入明确的 `runtime_reference_profile`；旧请求继续使用旧参考，旧结果不覆盖。固定正面矩阵已全部结束，本地服务已启用新提交策略。工作台重新提交辉夜抬臂后，313 帧捕获完成，原工件身份未变化，投影与几何异常仍明确保留。

辉夜抬臂原始失败已定位到 1.128125 秒、`layer-002-component-0000` 的第 222 个顶点。对完全相同工件应用独立存储参考后，313 帧对照通过，最大误差约 0.000164 px，setup 对照无可见像素缺失。原始理想几何仍有一项失败，因此候选仍不可视为动作质量通过。

失败捕获新增 `failure.json`，保存确切工件、Runtime/工具/脚本身份，以及附件、顶点、时间、期望/实际坐标和门槛。文件是诊断证据，不是成功报告。实测记录见 [验证证据](benchmark/m4-runtime-storage-v1.json)。

裙腰跟随候选使用 `autospine.character-reference-chunks/v2` 保存密集理想参考，避免大角色超过既有包体限制。
索引格式见 `schemas/character-reference-chunks-v2.schema.json`，分块内容见
`schemas/reference-chunk-envelope-v1.schema.json`。每块为 gzip/base64 的 JSON 封装，
按压缩文件摘要寻址，并检查解压长度与摘要；解压每块最多 64 MiB、合计最多 256 MiB。
这只改变证据的存储方式，不改采样、数值或导出骨架。Python 及官方捕获用的 Node 读取器兼容平铺、v1 和 v2；
生产捕获仍另算 Float32 存储参考，不能把无损压缩等同于降低精度。
