#!/usr/bin/env bash
# 一键启动 Story Digger Web：
#   默认（生产）：编译前端到 web/dist + 启动后端（FastAPI + 常驻 MCP）托管前端
#   --dev：前端起 Vite dev server（HMR），后端 uvicorn --reload（热加载）
#
# 用法：
#   ./start.sh                    # 生产：用默认配置 ~/.story-digger-agent/config.toml
#   ./start.sh --config X.toml    # 生产：透传自定义配置文件
#   ./start.sh --dev              # 开发：前端 HMR + 后端热加载（默认配置）
#   ./start.sh --dev --config X   # 开发：指定配置文件
#
# 退出前会按 Ctrl+C 结束；后端退出时自动清理常驻 MCP 子进程。
set -euo pipefail

# 脚本所在目录即仓库根（兼容从任意目录调用）
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

# 解析 --dev 标志，其余参数（如 --config）透传给后端。
DEV=0
EXTRA_ARGS=()
for arg in "$@"; do
  if [ "$arg" = "--dev" ]; then
    DEV=1
  else
    EXTRA_ARGS+=("$arg")
  fi
done

if [ "$DEV" -eq 1 ]; then
  # ---- 开发模式：前端 Vite（HMR）+ 后端 uvicorn --reload ----
  if [ ! -d "web/node_modules" ]; then
    echo "  （首次运行：安装前端依赖）"
    (cd web && npm install)
  fi

  echo "▶ 开发模式：启动前端 Vite dev server（http://localhost:5173，HMR）…"
  (cd web && npm run dev) &
  FE_PID=$!

  # Vite 就绪后打开浏览器提示；后端改动 src/** 会自动热重启。
  echo "▶ 开发模式：启动后端（uvicorn --reload，改 src/** 自动重启）…"
  # 收起子进程：后端与 MCP 都随本脚本退出。
  trap 'kill "$FE_PID" 2>/dev/null || true' EXIT INT TERM
  exec uv run python src/__main__.py --dev ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
fi

# ---- 生产模式：编译前端 + 启动后端托管构建产物 ----
echo "▶ 正在编译前端资源…"

if [ ! -d "web/node_modules" ]; then
  echo "  （首次运行：安装前端依赖）"
  (cd web && npm install)
fi

(cd web && npm run build)

echo "✓ 前端编译完成：web/dist"

echo "▶ 启动后端服务…"
exec uv run python src/__main__.py ${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}
