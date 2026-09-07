# 检查肘部 Mesh 面积收缩

`screen-mesh-area` 对精确来源的旧/新加权 Mesh 每 1° 检查 −90° 至 +90°，
输出独立内容地址的 `mesh-area-report/v1`，不改写既有权重、QA 或用户绑定决定。

```powershell
python -m autospine_workbench.benchmark screen-mesh-area `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --mesh ../tmp/r2b-mesh/alice-joint-plane-v2.json `
  --html ../tmp/r2b-mesh/alice-area-v1.html `
  --output ../tmp/r2b-mesh/alice-area-v1.json
```

`lingxian`、`crino` 同理。CLI 成功表示诊断生成成功，是否满足本项检查应读取每层
`status` 和 `reason_codes`；没有已选 Mesh 为 `not_evaluated`，不视为通过。
独立读取入口 `benchmark.mesh_area_cli.read_area_report` 重放来源并重新计算报告。

实验 profile 将面积比小于 0.5 标记 `mesh_area_compression`，大于 2 标记
`mesh_area_expansion`；翻转和原基础 QA 失败也会阻塞本项检查。
阈值尚未通过 Benchmark 校准，不产生发布权。统计包含所有三角形，收缩范围按
setup 面积加权，不以三角形数量作为占比，不通过删除透明边缘或加密网格改善统计。

页面将最小面积时刻的问题位置同步标在 setup 和变形线框上，悬停可查看三角形索引与面积比。
它不是纹理视觉金图或 Runtime 证据；接缝、独立腕部、复合动作和连续时间仍未验证。

四张真实手臂全网格最小面积比约 16.3%、22.9%、12.7%、12.4%，均需继续处理。
辅助诊断在不透明三角形中心也发现约 23%–29% 的面积保留率；局部重新求权重后的
Jacobian 仍有收缩，说明轮廓裁剪或单纯插点不能根治。
下一步比较肘部辅助骨/角度驱动 corrective deform，再用关节支撑点表达新的变形自由度。
保留原 LBS 基线，不能将替代混合算法的离线效果直接宣称为 Spine 可用输出。

[真实验证记录](benchmark/mesh-area-screen-2026-09-08.json)记录三份报告的地址、逐层状态和数值。
27 项相关测试通过，真实 CLI 来源重放、Schema、数值重算和 CAS 读回通过，Chrome 检查 Alice 页面。
未运行全量 Python/Web 测试或官方 Spine Runtime。
