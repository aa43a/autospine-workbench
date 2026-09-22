# 姿态素材任务包验证

2026-09-23，17 项相关测试通过：草稿、阶段验收与素材导出，包含字节保持、坐标转换、确定性 ZIP、摘要清单、旧证据及撤销修订拒绝。

实际工作台 Alice 任务 `motion-a7a946be55ee44169e8ccb6e0fe4baa7`，候选 `501ed517731d534f2a956bb9037fd686e08460e23110575d717f756e9c66a81d`：浏览器保存修订 4 的测试姿态草稿，刷新恢复，通过链接下载 ZIP，随后保存修订 5 撤销；旧修订下载返回 400。页面脚本错误 0。没有提交人工验收。

下载包的全部摘要核对通过，195×268 原纹理与候选 `images/layer-004.png` 及 `editor/images/layer-004.png` 字节完全一致。候选、源动作与动画未变化，没有重新捕获 Runtime。

证据位于 `localset/tmp/m4-motion-center/repair-material-v1/alice/`：`check.json`、`pose-material-request.zip`、`draft.png`。浏览器重放工具为 `tools/check-motion-repair-draft.mjs` 的 `pose_attachment` 模式。

任务包仅描述处理意图与已有异常，不证明必须补图，也不生成正确姿态。尚未实现回交素材、附件映射或修复构建，M4 原验收门槛保留。
