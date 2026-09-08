# 补齐头部部件绑定复核

`complete-layer-bindings` 为明确命名的眼白、虹膜、眉毛、睫毛、耳、鼻、嘴和头饰
新增跟随 `head` 的刚性候选。使用独立 `rigid-name-completion-v3` profile，
复用 v2 选项结构和存储；旧 profile、绑定地址、Mesh 与 Bake 不变。
这只是 setup 部件绑定，不是眨眼、口型 Attachment Switch。

```powershell
python -m autospine_workbench.benchmark complete-layer-bindings `
  --manifest docs/benchmark/manifest-frozen-v1.json --workspace .. `
  --draft ../tmp/r2b-multibone/alice-defaults-confirmed.json `
  --html ../tmp/r2b-completion/alice-v1.html `
  --draft-output ../tmp/r2b-completion/alice-draft-v1.json `
  --output ../tmp/r2b-completion/alice-bindings-v3.json
```

页面默认只显示待处理项。每层选择绑定动作与骨骼选项后，保存整份草稿；
取消筛选可以检查既有选择。支持撤销和恢复同来源草稿。
重新运行时附加 `--reviewed-draft <下载的草稿.json>`，并为 HTML、draft-output
指定新文件名，即可验证并封存修改。不同来源的草稿会明确失败。

只有每层完整候选内容未变时，旧草稿的选择才能复制到新草稿。
发生变化且旧记录不是 pending 时返回 `binding_completion_changed_reviewed_layer`；
不覆盖人工排除或其他既有决定。新头部候选全部 pending，authority 仍为 none。
空图层、隐藏层、画布外图层和阻塞骨架不会因名称匹配获得选项。

三个 development 角色的真实来源重放结果：

| 角色 | 总图层 | 保留既有绑定 | 新头部候选 | 其他待处理 |
| --- | ---: | ---: | ---: | ---: |
| Alice | 23 | 7 | 12 | 4 |
| 铃仙 | 21 | 7 | 12 | 2 |
| 琪露诺 | 18 | 5 | 7 | 6 |

新增 31 项候选尚未采用，原来的 43 项待处理并未因生成建议而变成已完成。
其他 12 项包括裙装、双侧肢体/鞋、物件、翅膀以及空/隐藏头饰。
后续先处理这些结构问题，再基于确认后的草稿重建 Mesh/Bake/角色组合来源链，
不能给旧 Mesh 替换一个 draft SHA 后继续使用。完整角色和官方 Runtime 仍未验收。

新增 Schema、纯分析/验证、来源重放 reader、CLI 和复核页面均已接入。
真实计数与地址见 [验证记录](benchmark/binding-completion-2026-09-08.json)。
