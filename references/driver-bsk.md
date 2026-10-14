# 备用驱动：bsk（browser-skill CLI）

**默认不用它。** 只在 chrome-devtools 不可用、或需要纯脚本无人值守批量时切过来。
它连的是用户日常那个已登录的浏览器，天然带登录态——这是它相对 chrome-devtools 的主要优势。
封装在 `scripts/bskw.py`。

## 启动

```bash
BSK_AUTO_START=0 bsk daemon start --foreground     # 必须跑在受管后台任务里
```

每次客户端调用都要重复 `BSK_AUTO_START=0`（不继承环境变量）。
端口每次启动可能变化，以 `bsk status --json` 为准。

```bash
BSK_AUTO_START=0 bsk session start          # 注意：没有 new 子命令
BSK_AUTO_START=0 bsk navigate <url>  --session <id> --tab-id <t> --json
BSK_AUTO_START=0 bsk snapshot       --session <id> --tab-id <t> --json
BSK_AUTO_START=0 bsk evaluate "<js>" --session <id> --tab-id <t> --json
BSK_AUTO_START=0 bsk click <css|@eN> --session <id> --tab-id <t> --json
BSK_AUTO_START=0 bsk tab list       --session <id> --json
```

`session start` 之后所有命令都要带 `--session <id>`。

## 坑（每一条都踩过）

### 1. BROWSER-SKILL-OVERLAY 会吃掉所有点击

特征：DOM 里出现 `data-bsk-overlay-blocking`，`z-index:2147483647`、`position:fixed`、满视口。
CSS / 内联样式压不住，**唯一解法：另起一个新 session**。

### 2. 点职位会不断新开详情标签页

取详情 tab 必须 `max(tab_id)`，处理完立刻 `tab close`。
曾经因为读最早那个 tab 的残留弹窗，17 条全被误判成「专属简历模板」。

### 3. 看不见的元素点不动

无可见尺寸的元素报 `permission_denied: element not visible`。
列表页 `.job-opt` 默认 0 尺寸。解法：注入样式给尺寸，或用 JS 打标记 + CSS 选择器点
（`bskw.Bsk.click_js`）。

### 4. 截图

`bsk screenshot --session X --json` 返回 `path`，**不支持 `--path`**。
排查视觉问题前先禁用 Dark Reader 之类扩展。

### 5. daemon 孤儿进程

`~/.bsk/daemon.json` 里的 pid 与真实进程不一致时，客户端误判「未运行」，
而该 daemon 不会重写状态文件。处理顺序：

1. `netstat` 找占用端口（如 52800）的 pid
2. 停掉它
3. 用受管后台任务重启（新 daemon 会自己写 daemon.json）

**不要手改 daemon.json 的 pid，没用。**

### 6. JS 与会话

- `evaluate` 的 JS 用 bash 单引号包时，JS 内只能出现双引号
- 超长 / 超时的 JS 会把 session 拖挂，宜拆短
- 长任务结束后会话可能失效，`bsk session list` 变空 → 重建即可，
  浏览器 instance_id 不变、**登录态保留**；重建后全局替换脚本里的 SESSION

### 7. 「申请职位」按钮必须轮询 + JS 兜底

这一条值几十个岗位。曾有一版只有 15 条成功、179 条被判「无申请按钮」，
但页面明明有按钮。根因：① navigate 后没等渲染就找；② **JS 检测到按钮，快照 ref 仍可能取不到**。

`bskw.Bsk.wait_button()` 已封装三层：JS 轮询 → 快照重复取 6 次 → JS click 兜底。
