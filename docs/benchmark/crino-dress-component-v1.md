# 琪露诺独立连衣裙组件候选

2026-09-15：复用分区和裙装编译核心，将当前混合 topwear 内的连衣裙送入可变形候选。

- 原四动作角色：`f368ff50e902753b87fe4f939b7f1b3d1e0ad34b653876817a1dbb525385e9d5`。
- 保留原父骨骼的分区：`58365165455c6f5b5ada36d9101f683d9cd5662c28445bf071e957ee385d8d2f`。
- 变形候选：`9d228edeb195401486c83377b06ec3f02418eb375e9a23625aa897e7249d84f2`。
- 选择区域：`layer-002-component-0000`；其余翼、挂饰与残余仍为 static_reference。
- 腰线候选原图 y=463，根部可见支持 `[false, true, true]`，不宣称已复核。
- 原图像字节保留，其他区域逐帧顶点保持不变；上身随候选 chest，裙摆三条双骨链。
- 官方 Runtime 1,028 帧，几何失败 0；idle、limb-flex-15、wave-left、walk 保留。

复核入口：`E:/proj/unusual/localset/tmp/crino-dress-component/runtime/skirt/index.html`。
实际报告 `capture-result.json` 与 Runtime `report.json` 位于同一输出目录。
检查了 walk 第 64 样本捕获图；这不替代用户阶段验收。

当前前景裙层仍未同步变形；第一条辅助根部支持不足、两层裙摆遮挡与连接均未通过完整验收。
下一步将候选接入工作台持久化构建配方，并处理前景裙层及共享腰部参数。
不新增人工确认、不授予发布权，不更新首批十角色完成数。

相关 Python 18 项通过；旧默认裙装生成器与修改前代码的输出字节逐项相等；
真实候选通过 `isolated-dress-candidate-v1` 报告合同校验。
