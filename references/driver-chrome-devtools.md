# 主驱动：chrome-devtools MCP

2026-10-14 实测。工具前缀 `mcp__chrome-devtools__*`。

## 工具用法

```jsonc
// 看页面列表（自检第一步）
list_pages                                     // 无参数

// 导航
navigate_page   {pageId, type:"url", url}
navigate_page   {pageId, type:"reload"}

// 读页面 / 取数据（主力，比 snapshot 便宜得多）
evaluate_script {pageId, function:"() => document.title"}
evaluate_script {pageId, function:"(el) => el.innerText", args:["uid-from-snapshot"]}

// 拿 uid（只在要点的时候调，输出很长）
take_snapshot   {pageId}
take_snapshot   {pageId, verbose:true}

// 点
click           {pageId, uid}
click           {pageId, uid, includeSnapshot:true}   // 点了直接看结果
```

## 实测表现

| 环节 | 结果 |
|---|---|
| 导航详情直链 | 通过 |
| 抓卡片（国聘 fiber / 智联 Vue） | 通过，**免登录**，100% 命中主键 |
| JD 边界切分 | 通过 |
| `take_snapshot` 拿 uid | **一次命中**，比 bsk 的 ref 稳 |
| `click` 投递按钮 | 通过 |
| 读弹窗 | 通过 |

## 已知边界

1. **开的是全新浏览器实例，不带登录态。** 这是唯一实质短板。
   国聘详情页是整页登录墙，智联详情页能开但 JD 被截断。
   **解决：让用户在实例里手动登录一次**，登录态会留下来。
2. **没有 HTTP 远程调试端口**（实测 9222/9223/9333 都不通），
   所以 Python 脚本无法直连 CDP 自驱动——浏览器交互只能由 agent 用工具逐步执行。
   这也是本 skill 把「浏览器操作」和「数据处理」分开的原因。
3. 未登录时点智联「立即投递」只弹登录框，不会真投递。
   别把这个当成"链路通了"的证据。

## 坑

1. **`function` 是 JSON 字符串**，正则里的 `\s` 要写成 `\\s`，否则正则失效还不报错。
2. **`take_snapshot` 输出极长**（一页几百个 uid）。别在循环里频繁调——
   先用 `evaluate_script` 判断状态，要点的时候再取快照。
3. **uid 会变**。每次 `take_snapshot` 后用**最新**那次的 uid，跨快照复用会点错。
4. **登录框和投递弹窗共用 `.a-modal` 类**（实测登录弹窗是
   `.a-modal.a-job-apply-workflow-close`）。判定分支必须先排除登录框，
   否则会误判成「需完善简历」。
5. 智联未登录 JD 被截断，门禁结果不可信——先登录再判。
6. `evaluate_script` 默认 `waitForStableDom: true`，纯读取可以传 `false` 提速。

## 与 bsk 的对照

| 维度 | chrome-devtools | bsk |
|---|---|---|
| 登录态 | 新实例，需手动登录一次 | 用日常浏览器，天然带登录态 |
| 元素定位 | uid 一次命中 | ref 偶发取不到，需 JS 兜底 |
| 遮罩 / overlay | 未观察到 | 有 `BROWSER-SKILL-OVERLAY`，只能重建 session |
| 脚本化批量 | 不行（无调试端口） | 可以（CLI 可 subprocess 调） |
| 会话稳定性 | 稳 | daemon 会掉、有孤儿进程 |

**默认用 chrome-devtools。只在 chrome-devtools 不可用、或需要完全无人值守脚本化时，才切 bsk。**
