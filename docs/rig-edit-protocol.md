# 图层编辑事务接入

本切片借鉴 Rev2D 的原子操作和结构化诊断设计，独立实现于现有 AutoSpine 合同上；没有引入 Rev2D 运行时或改写现有 RigIR。

## 使用

打开 `/motion-editor.html`，选择角色与动作，在“图层编辑 · 整段校正”中修改位置、旋转、缩放或绘制顺序。所有修改先经事务验证，再进入实时预览及现有编辑历史。顶部撤销／重做支持恢复；草稿和构建继续保存同一份 `slot-world-affine-v1` 快照。

失败时显示图层和属性位置，已知图层会自动选中。本批次不保存任何部分结果。构建端仍独立验证当前角色的实际附件，防止草稿指向旧图层或不支持的附件。

## 程序接口

`web/modules/rig-edit-operations.js` 导出纯函数 `applyRigEditOperations(snapshot, operations, {layers})`。编辑器的 `execute` 使用同一函数。操作支持：

- `transform`：`slot` 稳定名称与 `values` 中的 dx/dy/rotation/scaleX/scaleY。
- `reset`：清除指定 slot 的位置校正。
- `order`：完整 slot 顺序；空数组恢复来源顺序。
- `replace`：验证并恢复完整快照，用于历史恢复与批量重置。

成功结果包含 value、inverse 与 impact；失败结果包含原值和 diagnostics（code、operation、slot、path、message、hint）。调用端必须检查 ok 后才使用结果，不应持久化失败批次。

UI 的位置遵循现有 Spine 世界坐标（向右、向上，逆时针正角），不会照搬 Rev2D 的屏幕坐标约定。变换以已有 setup 中心为 pivot，作用于整段。这里不修改骨骼父子关系。

## 构建与验证

前端保存／构建仍走原有来源身份校验和 layer_edits 请求字段；无需迁移旧草稿。服务器错误增加 diagnostics，原 reason_code 保留。烘焙报告增加 edit_impact：变换需要 geometry/contact/occlusion/runtime，纯顺序修改需要 occlusion/runtime 的复核。

impact 描述修改依赖，execution 明确为 full_build。目前没有跳过完整构建、复用未验证的局部缓存，也没有新增 MCP 服务。后续增量调度可消费这些依赖，但必须绑定角色、来源、算法和编辑版本。

## 后台预检查与前后对比

页面“检查当前图层修改”调用 `POST /api/motions/<source-job>/layer-edit-check`，参数是 project_id、character_job_id、baseline、operations。Python 事务实现与浏览器有跨语言一致性测试。该接口既供页面使用，也可供自动程序调用；不要求浏览器或图形环境。

成功检查保存不可变、内容寻址的记录，绑定源任务快照和角色 artifact；失败批次不写入记录。返回的 receipt_sha256 可通过 `GET /api/motions/<source-job>/layer-edit-check/<sha256>` 读取，包含原值、操作、结果和逆操作。记录重复提交使用同一个地址。它仅证明结构和附件兼容性，不代表视觉通过。

页面构建自动预检查，并向既有 adapt 请求传入 layer_edit_receipt；后端重新验证记录哈希、源动作、角色版本和实际 layer_edits。一处不同即拒绝，不会靠旧检查放行新修改。构建结果保留检查记录标识。旧客户端不带该字段时继续执行原有独立校验，不改变旧草稿合同。

“对比修改前”只切换预览并暂停到当前时间，不清除草稿、不添加撤销步骤、不改变导出数据；继续编辑或恢复草稿自动退出对比。撤销仍使用顶部编辑历史。

## 2026-09-29 真实链路检查

Alice 的 breathing_idle 前 30 帧（1 秒）使用 layer-022 水平移动 3 px 的测试修改，预检查→独立构建→官方 Runtime→ZIP 下载完成。任务 `motion-77834bed2e23448e95c9a222ff142c72`，耗时 39.7 秒；333 帧 Runtime 几何检查通过，26 slots，零几何失败记录。检查记录为 `dda030d7aedffc75d721588a9ac0b0887d1b111dfa6a276e5d5a30bb22c090e9`。

该测试候选仍是 needs_changes：接触漂移、人工图层校正的表面接触与遮挡缺测均保留；不属于视觉验收，不覆盖历史接受记录。这是编辑和交付管线的验证样本，不是对完整动作支持范围的新增承诺。

## 验证范围

自动测试覆盖后续操作失败的整批回滚、逆操作、未知与不支持图层、字段定位、草稿序列化、固定／动态视角构建传递、实际加权网格烘焙和未修改区域保留。既有官方 Runtime 和阶段视觉验收保持原语义；本次测试不代表重新验收所有角色动作。
