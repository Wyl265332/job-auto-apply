# 驱动安装说明

本 skill 需要**至少一个浏览器驱动**。两个都装也行：主用 chrome-devtools，它挂了自动切 bsk。

## 一、chrome-devtools MCP（推荐）

Google 官方的 `chrome-devtools-mcp`，通过 Chrome DevTools Protocol 操控浏览器。
定位稳（无障碍树直接给 uid），没有后台进程烦恼。

### 装

不需要预先下载，MCP 客户端会用 `npx -y` 拉最新版本。把下面这段加进你的 MCP 配置文件：

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": ["-y", "chrome-devtools-mcp@latest", "--no-usage-statistics"]
    }
  }
}
```

Windows 上 `npx` 可能不在 PATH，需要写全路径，例如：

```json
"command": "C:\\Users\\<你>\\.workbuddy\\binaries\\node\\versions\\22.22.2-6\\npx.cmd"
```

完整模板见 `mcp/mcp-servers.example.json`。

### 验

让 AI 助手调一次 `list_pages`，能返回页面列表就算通。

### 已知限制

- **开的是全新浏览器实例，不带登录态。** 招聘站点必须你手动登录一次，
  登录态会留在实例里。这是全流程唯一必须人工的一步。
- **没有 HTTP 远程调试端口**（9222 等都不开），所以 Python 脚本无法自驱动，
  浏览器操作只能由 agent 逐步调工具完成。这也是本 skill 把「浏览器操作」和
  「数据处理」分开的原因。
- 撞上 BOSS 直聘 / 猎聘这类反爬站点会被踢成 `about:blank`，换平台，别硬刚。

## 二、bsk（备用）

Browser Skill 的 CLI，连的是你**日常那个已登录的浏览器**，天然带登录态。
代价：要管后台 daemon，且元素定位偶发取不到，需要 JS 兜底。

### 装

`with-drivers` 版本里带了 `bsk.exe`（在 `mcp/bsk/`）。

```powershell
# Windows：放到一个在 PATH 里的目录
Copy-Item mcp\bsk\bsk.exe "$env:USERPROFILE\.local\bin\bsk.exe"
$env:PATH += ";$env:USERPROFILE\.local\bin"
bsk --version
```

```bash
# macOS / Linux
sudo cp mcp/bsk/bsk /usr/local/bin/bsk && bsk --version
```

另外还需要在 Chrome / Edge 里装它的浏览器扩展并开启连接——这个只能手动，
脚本装不了。

### 启动

```bash
BSK_AUTO_START=0 bsk daemon start --foreground     # 必须跑在受管后台任务里
BSK_AUTO_START=0 bsk session start                 # 记下 session id
```

**每次调用都要带 `BSK_AUTO_START=0`**，客户端不继承这个环境变量。

### 已知坑

完整清单见 `references/driver-bsk.md`，最要命的三条：

1. `BROWSER-SKILL-OVERLAY` 会吃掉所有点击，CSS 压不住，**只能重建 session**
2. 点职位会不断新开标签页，取 tab 要用 `max(tab_id)`，用完立刻关
3. daemon 会出孤儿进程（`daemon.json` 的 pid 对不上），要 netstat 找占用端口的进程停掉再重启

## 三、两个都装

`config.json` 里写 `"driver": "both"`，主用 chrome-devtools，失败自动切 bsk。

## 隐私提醒

这两个驱动都是**在你自己的浏览器里、用你自己的登录态**操作。
不要把 cookie、密码、token 交给任何脚本，本 skill 的所有脚本也都不读这些东西。
