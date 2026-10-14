# bsk 二进制放这里

`with-drivers` 版本的压缩包里，这个文件应该是 `bsk.exe`（Windows）或 `bsk`（macOS/Linux）。

**纯 skill 版本不含这个文件**——直接用 chrome-devtools MCP 就够了，也更省事。

## 放进来之后的用法

```powershell
# Windows
Copy-Item bsk.exe "$env:USERPROFILE\.local\bin\bsk.exe"
```

```bash
# macOS / Linux
sudo cp bsk /usr/local/bin/bsk && chmod +x /usr/local/bin/bsk
```

然后回到上级目录跑 `mcp/install-drivers.ps1`（或 `.sh`）做体检。

## 注意

- bsk 是**第三方二进制**，本仓库不提供它的源码，也不对它的行为负责
- 只从官方渠道获取，别用别人转发的 exe
- 装完还需要**在浏览器里装它的扩展并开启连接**，这一步脚本做不到
- 它的 daemon 需要跑在受管后台任务里：
  `BSK_AUTO_START=0 bsk daemon start --foreground`
- 已知坑（overlay 吃点击、tab 累积、daemon 孤儿进程）见 `references/driver-bsk.md`
