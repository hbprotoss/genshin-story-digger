#!/usr/bin/env bash
# 一键启动 Story Digger Web：
#   1) 安装前端依赖（如缺）并编译前端到 web/dist
#   2) 启动后端（FastAPI + 常驻 MCP），并托管编译好的前端资源
#
# 用法：
#   ./start.sh                    # 用默认配置 ~/.story-digger-agent/config.toml
#   ./start.sh --config X.toml    # 透传自定义配置文件给后端
#
# 退出前会按 Ctrl+C 结束；后端退出时自动清理常驻 MCP 子进程。
set -euo pipefail

# 脚本所在目录即仓库根（兼容从任意目录调用）
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

echo "▶ 正在编译前端资源…"

if [ ! -d "web/node_modules" ]; then
  echo "  （首次运行：安装前端依赖）"
  (cd web && npm install)
fi

(cd web && npm run build)

echo "✓ 前端编译完成：web/dist"

echo "▶ 启动后端服务…"
exec uv run python src/__main__.py "$@"
