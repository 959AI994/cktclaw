#!/bin/bash
_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(conda shell.bash hook)"
conda activate cktclaw
source "${_DIR}/.env"
echo "✓ CktClaw 环境已激活 — 输入 cktclaw 启动"
