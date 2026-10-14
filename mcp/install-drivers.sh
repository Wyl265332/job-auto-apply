#!/usr/bin/env bash
# 一键安装驱动（macOS / Linux）
# 用法：bash mcp/install-drivers.sh
#
# chrome-devtools 是 npm 包，不需要下载，改 MCP 配置即可（见 mcp/README.md）。
# 这个脚本只负责：把 bsk 放进 PATH、确认 node/npx 可用、跑一次体检。

set -e
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== 检查 node / npx =="
if command -v npx >/dev/null 2>&1; then
  echo "[OK] npx: $(command -v npx)"
  echo "     chrome-devtools MCP 可以直接用：npx -y chrome-devtools-mcp@latest"
else
  echo "[缺失] npx 不在 PATH。装 Node.js 20+ 后重试（https://nodejs.org）"
fi

echo ""
echo "== 安装 bsk（备用驱动）=="
SRC="$HERE/bsk/bsk"
if [ -f "$SRC" ]; then
  DEST="/usr/local/bin/bsk"
  if [ -w /usr/local/bin ]; then
    cp "$SRC" "$DEST"; chmod +x "$DEST"
  else
    sudo cp "$SRC" "$DEST"; sudo chmod +x "$DEST"
  fi
  echo "[OK] bsk -> $DEST"
  bsk --version
else
  echo "[跳过] 没找到 $SRC —— 你下载的是纯 skill 包（不含驱动二进制）。"
  echo "        要 bsk 的话去官方渠道下载，或直接用 chrome-devtools（推荐）。"
fi

echo ""
echo "下一步（必须手动）："
echo "  1. chrome-devtools：把 mcp/mcp-servers.example.json 里的条目合并进你的 MCP 配置"
echo "  2. bsk：在浏览器里装它的扩展并开启连接"
echo "  3. 回到 skill 目录跑：python scripts/workflow.py doctor"
