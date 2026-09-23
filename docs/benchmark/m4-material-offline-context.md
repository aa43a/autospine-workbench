# 姿态素材任务包的离线上下文

素材下载增加 `pose-preview.html`：嵌入经现有读取链核对的完整角色、图集及官方 Runtime，打开后选择原异常动作、时间和三角形。用户可拖动前后帧、隔离部件、恢复整角色。画面展示实际失败候选，不是期望轮廓；不生成素材或改变验收。

`request.json` 回交合同保持不变，播放器另列入包内摘要清单。回交验证不重新打包预览，也不新增 Runtime 环境依赖。下载预览必须通过原候选与 Runtime 身份核对，无法读取时明确失败。

12 项相关测试通过，覆盖源/事件身份、包清单、回交合同、撤销与过期草稿。真实候选 `501ed517731d534f2a956bb9037fd686e08460e23110575d717f756e9c66a81d` 在本地 file 页面零网络加载，通过 `layer-004`、3.966667 秒、实际三角形高亮与反向拖动检查，无脚本错误。首次浏览器测试按浮点秒数精确相等导致超时，改为微秒比较后通过，动画未调整。

复现工具：`tools/m4_material_preview_probe.py` 只读生成样例，`tools/check-motion-material-offline.mjs` 在实际 Chrome/WebGL 中验证。样例位于 `tmp/material-offline-v1/pose-preview.html`。这不是新视觉验收，不证明当前问题必然需要补图。

## 真实工作台下载验证（2026-09-24）

服务在无活跃动作任务时重启加载更新，155 条任务状态一致。通过真实 HTTP 草稿/下载接口生成 14,254,070 字节 ZIP，包含七个文件，完整核对 inventory 摘要。下载包中的 `pose-preview.html` 通过 Chrome 离线零网络播放、候选身份、3.966667 秒三角形定位和反向拖动检查。

仅对 `motion-a7a946be55ee44169e8ccb6e0fe4baa7` 已撤销事件建立标明测试用途的临时草稿 r30，下载后以 r31 撤销，原历史保留；没有构建、素材回交或视觉接受。`tools/m4_material_download_check.py` 会拒绝覆盖现存有效处理方案，下载后在 finally 撤销自己的草稿。证据位于 `tmp/material-download-v1/report.json`。
