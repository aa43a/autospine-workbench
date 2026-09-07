# 20 角色 Benchmark 标注流程

已收到上级目录的 12 个新增 PSD（alice、bayunlan、crino、flandre、huiye、
lingxian、lumia、meihong、sakuya、uuz、yaomeng、yaomeng1）。尚未完成逐层审计；
yaomeng/yaomeng1 是否是同角色变体待标注，12 文件不等于 12 独立角色。不得生成虚构来源 SHA、
占位“已审核关节”或使用示意图宣称真实角色验收通过。

已核对 `../png` 下有 20 张原始 PNG；下一步记录真实字节身份并建立 PSD 对应关系。

首批冻结 10 个：3 个开发 fixture、4 个可见测试、3 个 holdout；第二批 10 个
待首批算法稳定后加入。split 在开始调参前记录，holdout 不用于逐图调参。
角色名称不决定难度，必须观察实际图像后标记 simple/medium/hard/unsupported。

每份标注填写以下模板，空值代表尚未标注，不能视为已通过：

```json
{
  "character_id": null,
  "dataset_split": null,
  "source_sha256": null,
  "generation_metadata": {},
  "complexity": null,
  "complexity_tags": [],
  "expected_core_layers": [],
  "reviewed_joints": {},
  "supported_motion_set": [],
  "rights": {"usage": "internal_test"},
  "annotation_status": "pending"
}
```

录入时计算真实源图字节 SHA，记录画布、角色 bbox、镜像状态与关节坐标系。
源文件改变必须新建身份；历史标注和测量不能自动继承。人工关节记录坐标、
来源、操作者、复核时间与不可观测原因，不把自动推断复制为 ground truth。
每次测试固定代码提交、参数/profile、数据 split、耗时与失败 reason code。

将预先分配的样本全数纳入分母，包括失败和阻塞样本。分别报告：
自动采用正确率及抽查数量、覆盖率、关节误差/角色高度、人工复核 P50/P90、
端到端成功率、静默错误、Runtime 视觉失败。机制 stub 与真实 Runtime 分开。

失败分类固定为：input_not_riggable、see_through_layer_missing、semantic_ambiguous、
joint_unobservable、layer_requires_split、mesh_topology_failure、weight_failure、
seam_failure、motion_out_of_plane、draw_order_ambiguous、attachment_missing、
secondary_motion_unstable、runtime_export_failure。

数据集 Schema/validator 和度量工具属于 AS-009/AS-008 后续实现；本文件仅提供
标注流程与输入模板，不宣称已建成或验证了 20 角色数据集。
