# 保存与恢复绑定复核草稿

打开 `../tmp/r2b-bindings/{alice,lingxian,crino}-review-v2.html`。
每层选择处理方式：尚未处理、选择候选骨骼、需要拆层、需要语义复核、草稿中排除。
只有已有候选选项的图层可选择绑定；其它图层可填写结构问题，不能借草稿绕过上游阻塞。
拆层、语义复核和排除必须填写备注，备注支持换行。所有初始记录均为尚未处理。

页面顶部的“保存整份草稿”下载JSON，“恢复草稿”读取已有文件，“撤销上一步”恢复最近编辑。
这三个操作只影响本地草稿，不提交正式采用。浏览器刷新前请保存；没有后台自动保存。
恢复时核对绑定候选地址、层清单、顺序、骨骼范围和字段类型，拒绝错误角色或旧候选的文件，
导入失败保留当前草稿。骨架、语义或图层变化后需要重新生成候选，不能直接套用旧决定。

需要把下载的草稿封存并生成可继续编辑的页面时，在仓库目录运行：

```powershell
python -m autospine_workbench.benchmark build-region-bindings `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --skeleton ../tmp/r2b-skeleton/crino-v2.json `
  --draft C:/Users/Administrator/Downloads/region-binding-draft.json `
  --draft-output ../tmp/r2b-bindings/crino-reviewed-draft.json `
  --html ../tmp/r2b-bindings/crino-resumed.html
```

省略 `--draft` 会准备全pending的草稿。`--draft-output` 导出草稿，原有 `--output` 仍导出绑定候选。
CLI封存前验证完整源闭包；`read_binding_draft` 再读取候选、骨架、标注和实际源文件后核验草稿。
相同输入保持相同地址，导出文件已有不同内容时拒绝覆盖，请选新名称。

本切片准备了三个真实角色共62条pending记录，未替用户绑定、排除或声明拆层完成。
`requires_split` 只记录任务，并未修改PNG；`semantic_review` 只记录问题，并未更新正式语义。
页面保存成功或所有记录已填写，也不构成独立GT、正式绑定采用或生产导出权。
下一切片需要把明确复核结果接到异常处理与region预览编译。

验证：13项相关测试通过，包含草稿Schema/语义、Node执行的浏览器校验逻辑、
CLI保存恢复和源图变化拒绝，以及文件长度门禁。Chrome已渲染检查铃仙实际编辑页。
本切片未运行全量Python/Web或Spine Runtime测试，未修改骨架及绑定候选算法。
