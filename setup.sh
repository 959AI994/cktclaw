#!/bin/bash
################################################################################
# CktClaw — 一键部署脚本
#
# 用法:
#   bash setup.sh            # 完整安装（推荐）
#   bash setup.sh --minimal  # 仅 Python 依赖，跳过 EDA 工具编译
#   bash setup.sh --help     # 帮助
#
# 执行内容:
#   1. 创建 Conda 环境 (Python 3.10)
#   2. pip install -e .（CktClaw 本体 + 依赖）
#   3. 下载 oss-cad-suite（Yosys / ABC / Verilator / SymbiYosys / nextpnr …）
#   4. 从源码编译 OpenSTA
#   5. 克隆 digital-chip-design-agents（14 域 Orchestrator）
#   6. 克隆 AI4EDA-OpenABC-Data-Toolkit
#   7. 生成 .env + activate.sh
#   8. 验证安装
################################################################################

set -e

# ── 颜色 ─────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC}    $1"; }
log_success() { echo -e "${GREEN}[OK]${NC}      $1"; }
log_warning() { echo -e "${YELLOW}[WARN]${NC}    $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC}   $1"; }
log_step()    { echo -e "\n${CYAN}━━━ $1 ━━━${NC}"; }

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONDA_ENV="cktclaw"
PYTHON_VER="3.10"
DEPS_DIR="${PROJECT_ROOT}/deps"
MINIMAL=false

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ── 参数解析 ──────────────────────────────────────────────────────────
for arg in "$@"; do
    case "$arg" in
        --minimal) MINIMAL=true ;;
        --help|-h)
            echo "Usage: bash setup.sh [--minimal] [--help]"
            echo ""
            echo "  --minimal   Skip EDA tool installation (Python deps only)"
            echo "  --help      Show this message"
            exit 0
            ;;
    esac
done

# ── Banner ────────────────────────────────────────────────────────────
cat << 'BANNER'

  ██████╗██╗  ██╗████████╗ ██████╗██╗      █████╗ ██╗    ██╗
 ██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██║     ██╔══██╗██║    ██║
 ██║     █████╔╝    ██║   ██║     ██║     ███████║██║ █╗ ██║
 ██║     ██╔═██╗    ██║   ██║     ██║     ██╔══██║██║███╗██║
 ╚██████╗██║  ██╗   ██║   ╚██████╗███████╗██║  ██║╚███╔███╔╝
  ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

  One-Click Setup
BANNER

echo ""
log_info "项目路径: ${PROJECT_ROOT}"
log_info "模式: $(${MINIMAL} && echo '精简（跳过 EDA 工具）' || echo '完整安装')"
echo ""

# ══════════════════════════════════════════════════════════════════════
# Step 1: Conda 环境
# ══════════════════════════════════════════════════════════════════════
log_step "Step 1/6: Conda 环境"

if ! command_exists conda; then
    log_error "未检测到 Conda"
    log_info "请先安装 Miniconda:"
    log_info "  wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh"
    log_info "  bash Miniconda3-latest-Linux-x86_64.sh"
    exit 1
fi
log_success "Conda: $(conda --version)"

if conda env list 2>/dev/null | grep -q "^${CONDA_ENV} "; then
    log_warning "环境 '${CONDA_ENV}' 已存在，跳过创建"
else
    log_info "创建 Conda 环境: ${CONDA_ENV} (Python ${PYTHON_VER})"
    conda create -n ${CONDA_ENV} python=${PYTHON_VER} -y
    log_success "环境创建完成"
fi

eval "$(conda shell.bash hook)"
conda activate ${CONDA_ENV}
log_success "已激活: $(python --version) @ $(which python)"

# ══════════════════════════════════════════════════════════════════════
# Step 2: 安装 CktClaw（pip install -e .）
# ══════════════════════════════════════════════════════════════════════
log_step "Step 2/6: 安装 CktClaw"

cd "${PROJECT_ROOT}"
pip install --upgrade pip -q

log_info "安装 CktClaw + 核心依赖..."
pip install -e . -q

log_info "安装额外推荐包..."
pip install pydantic aiosqlite networkx -q

log_success "cktclaw 命令已注册: $(which cktclaw)"

# ══════════════════════════════════════════════════════════════════════
# Step 3: EDA 工具
# ══════════════════════════════════════════════════════════════════════
log_step "Step 3/6: EDA 工具"

mkdir -p "${DEPS_DIR}"

if ${MINIMAL}; then
    log_warning "精简模式，跳过 EDA 工具安装"
else
    # ── 3a: oss-cad-suite (Yosys, ABC, Verilator, SymbiYosys, nextpnr …) ──
    OSS_DIR="${DEPS_DIR}/oss-cad-suite"
    if [ -d "${OSS_DIR}" ] && [ -x "${OSS_DIR}/bin/yosys" ]; then
        log_success "oss-cad-suite 已存在，跳过下载"
    else
        log_info "下载 oss-cad-suite（含 Yosys / ABC / Verilator / SymbiYosys / nextpnr）..."
        ARCH=$(uname -m)
        OS=$(uname -s | tr '[:upper:]' '[:lower:]')
        if [[ "$OS" == "darwin" ]]; then
            PLATFORM="darwin-${ARCH}"
        else
            PLATFORM="linux-${ARCH}"
        fi

        # 获取最新 release 下载链接
        OSS_URL="https://github.com/YosysHQ/oss-cad-suite-build/releases/latest/download/oss-cad-suite-${PLATFORM}-$(date +%Y%m%d).tgz"
        OSS_FALLBACK="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-12-23/oss-cad-suite-${PLATFORM}-20241223.tgz"

        TARBALL="${DEPS_DIR}/oss-cad-suite.tgz"
        log_info "尝试下载: ${OSS_URL}"
        if ! wget -q --show-progress -O "${TARBALL}" "${OSS_URL}" 2>/dev/null && \
           ! curl -fSL -o "${TARBALL}" "${OSS_URL}" 2>/dev/null; then
            log_warning "最新版下载失败，尝试已知稳定版..."
            wget -q --show-progress -O "${TARBALL}" "${OSS_FALLBACK}" 2>/dev/null || \
                curl -fSL -o "${TARBALL}" "${OSS_FALLBACK}" || {
                log_error "oss-cad-suite 下载失败，请手动下载:"
                log_info "  https://github.com/YosysHQ/oss-cad-suite-build/releases"
                log_info "  解压到 ${DEPS_DIR}/oss-cad-suite/"
            }
        fi

        if [ -f "${TARBALL}" ]; then
            log_info "解压 oss-cad-suite..."
            tar xzf "${TARBALL}" -C "${DEPS_DIR}"
            rm -f "${TARBALL}"
            log_success "oss-cad-suite 安装完成"
        fi
    fi

    # 添加 oss-cad-suite 到 PATH
    if [ -d "${OSS_DIR}/bin" ]; then
        export PATH="${OSS_DIR}/bin:${PATH}"
        TOOL_COUNT=0
        for tool in yosys abc verilator sby nextpnr-ice40; do
            if command_exists "$tool"; then
                TOOL_COUNT=$((TOOL_COUNT + 1))
            fi
        done
        log_success "oss-cad-suite: ${TOOL_COUNT}/5 核心工具可用"
    fi

    # ── 3b: OpenSTA（oss-cad-suite 不含，需单独编译）──
    if command_exists sta; then
        log_success "OpenSTA 已安装: $(sta -version 2>&1 | head -1 || echo 'ok')"
    else
        if command_exists cmake && command_exists make; then
            log_info "从源码编译 OpenSTA..."
            cd "${DEPS_DIR}"
            if [ ! -d "OpenSTA" ]; then
                git clone --depth 1 https://github.com/The-OpenROAD-Project/OpenSTA.git
            fi
            cd OpenSTA && mkdir -p build && cd build
            cmake .. -DCMAKE_INSTALL_PREFIX="${DEPS_DIR}/opensta-install" -DCMAKE_BUILD_TYPE=Release 2>&1 | tail -3
            make -j"$(nproc)" 2>&1 | tail -3
            make install 2>&1 | tail -1
            export PATH="${DEPS_DIR}/opensta-install/bin:${PATH}"
            log_success "OpenSTA 编译完成"
        else
            log_warning "缺少 cmake/make，跳过 OpenSTA 编译"
            log_info "安装: sudo apt-get install cmake build-essential tcl-dev"
        fi
    fi
fi

# ══════════════════════════════════════════════════════════════════════
# Step 4: digital-chip-design-agents（14 域 Orchestrator 模板）
# ══════════════════════════════════════════════════════════════════════
log_step "Step 4/6: Chip Design Agents"

AGENTS_DIR="${DEPS_DIR}/digital-chip-design-agents"
if [ -d "${AGENTS_DIR}/plugins" ]; then
    log_success "digital-chip-design-agents 已存在"
else
    log_info "克隆 digital-chip-design-agents..."
    git clone --depth 1 https://github.com/chuanseng-ng/digital-chip-design-agents.git "${AGENTS_DIR}"
    log_success "14 域 Orchestrator 模板就绪"
fi

# ══════════════════════════════════════════════════════════════════════
# Step 5: AI4EDA-OpenABC-Data-Toolkit
# ══════════════════════════════════════════════════════════════════════
log_step "Step 5/6: AI4EDA Toolkit"

AI4EDA_DIR="${DEPS_DIR}/AI4EDA-OpenABC-Data-Toolkit"
if [ -d "${AI4EDA_DIR}" ]; then
    log_success "AI4EDA Toolkit 已存在"
else
    log_info "克隆 AI4EDA-OpenABC-Data-Toolkit..."
    git clone --depth 1 https://github.com/959AI994/AI4EDA-OpenABC-Data-Toolkit.git "${AI4EDA_DIR}"
fi

cd "${AI4EDA_DIR}"
pip install -e . -q 2>/dev/null || log_warning "AI4EDA Toolkit pip install 失败（torch-geometric 可能需要手动安装）"
log_success "AI4EDA Toolkit 就绪"

# ══════════════════════════════════════════════════════════════════════
# Step 6: 生成 .env + activate.sh
# ══════════════════════════════════════════════════════════════════════
log_step "Step 6/6: 环境配置"

cd "${PROJECT_ROOT}"

# ── .env ──
cat > "${PROJECT_ROOT}/.env" << ENVEOF
# CktClaw 环境变量 — 由 setup.sh 自动生成 ($(date +%Y-%m-%d))

# EDA 工具路径
export PATH="${DEPS_DIR}/oss-cad-suite/bin:${DEPS_DIR}/opensta-install/bin:\${PATH}"

# Orchestrator 模板
export CHIP_AGENTS_ROOT="${AGENTS_DIR}/plugins"

# AI4EDA 工具
export AI4EDA_BIN="${AI4EDA_DIR}/ai4eda-toolkit"

# DeepSeek API（请替换为你的 key）
# export DEEPSEEK_API_KEY="sk-xxx"
ENVEOF

log_success "已生成: .env"

# ── activate.sh ──
cat > "${PROJECT_ROOT}/activate.sh" << 'ACTEOF'
#!/bin/bash
_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
eval "$(conda shell.bash hook)"
conda activate cktclaw
source "${_DIR}/.env"
echo "✓ CktClaw 环境已激活 — 输入 cktclaw 启动"
ACTEOF
chmod +x "${PROJECT_ROOT}/activate.sh"
log_success "已生成: activate.sh"

# ══════════════════════════════════════════════════════════════════════
# 验证
# ══════════════════════════════════════════════════════════════════════
echo ""
log_step "验证安装"

source "${PROJECT_ROOT}/.env"

# Python
python -c "from cktclaw.main import main; print('  cktclaw 模块导入 ✓')" 2>/dev/null || \
    log_warning "cktclaw 模块导入失败"

# cktclaw 命令
if command_exists cktclaw; then
    log_success "cktclaw 命令可用: $(which cktclaw)"
else
    log_warning "cktclaw 命令未找到（尝试 pip install -e . 后重试）"
fi

# EDA 工具
if ! ${MINIMAL}; then
    echo ""
    FOUND=0; TOTAL=0
    for tool in yosys abc verilator sta sby nextpnr-ice40; do
        TOTAL=$((TOTAL + 1))
        if command_exists "$tool"; then
            FOUND=$((FOUND + 1))
            log_success "$tool"
        else
            log_warning "$tool — 未检测到"
        fi
    done
    echo ""
    log_info "EDA 工具: ${FOUND}/${TOTAL} 可用"
fi

# Orchestrator
if [ -d "${AGENTS_DIR}/plugins/synthesis" ]; then
    DOMAINS=$(ls -d "${AGENTS_DIR}/plugins"/*/ 2>/dev/null | wc -l)
    log_success "Orchestrator: ${DOMAINS} 个芯片设计领域"
else
    log_warning "Orchestrator 模板未找到"
fi

# AI4EDA
if [ -f "${AI4EDA_DIR}/ai4eda-toolkit" ]; then
    log_success "AI4EDA Toolkit"
else
    log_warning "AI4EDA Toolkit 未找到"
fi

# ══════════════════════════════════════════════════════════════════════
# 完成
# ══════════════════════════════════════════════════════════════════════
cat << DONE

╔══════════════════════════════════════════════════════════════════╗
║                                                                  ║
║   ✅  CktClaw 安装完成！                                        ║
║                                                                  ║
║   下次使用：                                                     ║
║     $ source activate.sh                                         ║
║     $ cktclaw                                                    ║
║                                                                  ║
║   DeepSeek 云端引擎（推荐）：                                    ║
║     编辑 .env 文件，填入 DEEPSEEK_API_KEY                        ║
║                                                                  ║
║   文档：README.md                                                ║
║   问题：https://github.com/959AI994/cktclaw/issues               ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝

DONE
