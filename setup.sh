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
#   7. 克隆 verilog-generator + FPGA-Agent-skills
#   8. 生成 .env + activate.sh
#   9. 验证安装
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
log_step "Step 1/8: Conda 环境"

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
log_step "Step 2/8: 安装 CktClaw"

cd "${PROJECT_ROOT}"
pip install --upgrade pip -q

log_info "安装 CktClaw + 核心依赖..."
pip install -e . -q

# 统一安装 PyTorch/CUDA 栈（避免 NCCL/ABI 冲突）
log_info "清理可能冲突的 PyTorch/CUDA/PyG 包..."
pip uninstall -y \
    torch torchvision torchaudio \
    torch_cluster torch_scatter torch_sparse \
    nvidia-nccl-cu12 nvidia-cublas-cu12 nvidia-cuda-runtime-cu12 nvidia-cudnn-cu12 \
    >/dev/null 2>&1 || true

log_info "安装 PyTorch cu128 官方轮子..."
pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 \
    --index-url https://download.pytorch.org/whl/cu128 -q

log_info "安装 requirements.txt 依赖..."
pip install -r "${PROJECT_ROOT}/requirements.txt" -q

log_info "安装 PyG 扩展依赖（官方 wheel 源）..."
PYG_WHL="https://data.pyg.org/whl/torch-2.8.0+cu128.html"
pip install -f "${PYG_WHL}" torch_cluster torch_scatter torch_sparse torch-geometric -q || {
    log_error "PyG 扩展安装失败，请检查网络/CUDA 兼容性"
    log_info "可手动执行: pip install -f ${PYG_WHL} torch_cluster torch_scatter torch_sparse torch-geometric"
    exit 1
}

log_success "cktclaw 命令已注册: $(which cktclaw)"

# ══════════════════════════════════════════════════════════════════════
# Step 3: EDA 工具
# ══════════════════════════════════════════════════════════════════════
log_step "Step 3/8: EDA 工具"

mkdir -p "${DEPS_DIR}"
OSS_DIR="${DEPS_DIR}/oss-cad-suite"

# 优先探测本机已有 oss-cad-suite，避免重复下载
for candidate in \
    "${OSS_DIR}" \
    "${HOME}/.cktclaw-tools/oss-cad-suite" \
    "${HOME}/oss-cad-suite" \
    "/opt/oss-cad-suite"; do
    if [ -x "${candidate}/bin/yosys" ]; then
        OSS_DIR="${candidate}"
        break
    fi
done

# 若 PATH 中已有 yosys，尝试反推其根目录
if [ ! -x "${OSS_DIR}/bin/yosys" ] && command_exists yosys; then
    YOSYS_BIN="$(command -v yosys)"
    YOSYS_ROOT="$(cd "$(dirname "${YOSYS_BIN}")/.." && pwd)"
    if [ -x "${YOSYS_ROOT}/bin/yosys" ]; then
        OSS_DIR="${YOSYS_ROOT}"
    fi
fi

if ${MINIMAL}; then
    log_warning "精简模式，跳过 EDA 工具安装"
else
    # ── 3a: oss-cad-suite (Yosys, ABC, Verilator, SymbiYosys, nextpnr …) ──
    if [ -d "${OSS_DIR}" ] && [ -x "${OSS_DIR}/bin/yosys" ]; then
        log_success "发现现有 oss-cad-suite，跳过下载: ${OSS_DIR}"
    else
        log_info "下载 oss-cad-suite（含 Yosys / ABC / Verilator / SymbiYosys / nextpnr）..."
        ARCH=$(uname -m)
        OS=$(uname -s | tr '[:upper:]' '[:lower:]')
        if [[ "$OS" == "darwin" ]]; then
            PLATFORM="darwin-${ARCH}"
        else
            PLATFORM="linux-${ARCH}"
        fi

        # 获取 release 下载链接（不再用本地日期拼接，避免 404）
        OSS_FALLBACK="https://github.com/YosysHQ/oss-cad-suite-build/releases/download/2024-12-23/oss-cad-suite-${PLATFORM}-20241223.tgz"

        TARBALL="${DEPS_DIR}/oss-cad-suite.tgz"
        # 通过 GitHub API 获取该平台最新可用资产，失败时回退到稳定版
        OSS_URL=""
        API_URL="https://api.github.com/repos/YosysHQ/oss-cad-suite-build/releases/latest"
        if command_exists curl; then
            OSS_URL="$(curl -fsSL "${API_URL}" | grep -Eo "https://[^\" ]*oss-cad-suite-${PLATFORM}-[0-9]{8}\.tgz" | head -n1 || true)"
        fi
        if [ -z "${OSS_URL}" ]; then
            log_warning "无法解析最新 release 资产，使用已知稳定版..."
            OSS_URL="${OSS_FALLBACK}"
        fi

        log_info "尝试下载: ${OSS_URL}"
        if ! wget -q --show-progress -O "${TARBALL}" "${OSS_URL}" 2>/dev/null && \
           ! curl -fSL -o "${TARBALL}" "${OSS_URL}" 2>/dev/null; then
            if [ "${OSS_URL}" != "${OSS_FALLBACK}" ]; then
                log_warning "最新版下载失败，尝试已知稳定版..."
                if ! wget -q --show-progress -O "${TARBALL}" "${OSS_FALLBACK}" 2>/dev/null && \
                   ! curl -fSL -o "${TARBALL}" "${OSS_FALLBACK}" 2>/dev/null; then
                    rm -f "${TARBALL}"
                    log_error "oss-cad-suite 下载失败，请手动下载:"
                    log_info "  https://github.com/YosysHQ/oss-cad-suite-build/releases"
                    log_info "  解压到 ${DEPS_DIR}/oss-cad-suite/"
                    exit 1
                fi
            else
                rm -f "${TARBALL}"
                log_error "oss-cad-suite 下载失败，请手动下载:"
                log_info "  https://github.com/YosysHQ/oss-cad-suite-build/releases"
                log_info "  解压到 ${DEPS_DIR}/oss-cad-suite/"
                exit 1
            fi
        fi

        if [ -f "${TARBALL}" ]; then
            if ! tar tzf "${TARBALL}" >/dev/null 2>&1; then
                rm -f "${TARBALL}"
                log_error "下载文件损坏或非有效 tar.gz，请重试或手动下载"
                exit 1
            fi
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
log_step "Step 4/8: Chip Design Agents"

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
log_step "Step 5/8: AI4EDA Toolkit"

AI4EDA_DIR="${DEPS_DIR}/AI4EDA-OpenABC-Data-Toolkit"
if [ -d "${AI4EDA_DIR}" ]; then
    log_success "AI4EDA Toolkit 已存在"
else
    log_info "克隆 AI4EDA-OpenABC-Data-Toolkit..."
    git clone --depth 1 https://github.com/959AI994/AI4EDA-OpenABC-Data-Toolkit.git "${AI4EDA_DIR}"
fi

cd "${AI4EDA_DIR}"
pip install -e . -q 2>/dev/null || log_warning "AI4EDA Toolkit pip install 失败（torch-geometric 可能需要手动安装）"

# 确保所有入口脚本可执行（缺少 +x 会导致"Permission denied"运行时错误）
find "${AI4EDA_DIR}" -maxdepth 2 \( -name "ai4eda-toolkit" -o -name "*.sh" \) \
    -type f ! -executable -exec chmod +x {} \; \
    -exec log_info "已授权可执行: {}" \;
log_success "AI4EDA Toolkit 就绪: ${AI4EDA_DIR}/ai4eda-toolkit"

# ══════════════════════════════════════════════════════════════════════
# Step 6: verilog-generator + FPGA-Agent-skills
# ══════════════════════════════════════════════════════════════════════
log_step "Step 6/8: Verilog Generator + FPGA Agent Skills"

VERILOG_GEN_DIR="${DEPS_DIR}/verilog-generator"
if [ -f "${VERILOG_GEN_DIR}/SKILL.md" ]; then
    log_success "verilog-generator 已存在"
else
    log_info "克隆 verilog-generator..."
    git clone --depth 1 https://github.com/Eriemon/verilog-generator.git "${VERILOG_GEN_DIR}"
    log_success "verilog-generator 就绪"
fi

FPGA_SKILLS_DIR="${DEPS_DIR}/FPGA-Agent-skills"
if [ -f "${FPGA_SKILLS_DIR}/vivado-tcl/SKILL.md" ]; then
    log_success "FPGA-Agent-skills 已存在"
else
    log_info "克隆 FPGA-Agent-skills..."
    git clone --depth 1 https://github.com/adeleempurpled290/FPGA-Agent-skills.git "${FPGA_SKILLS_DIR}"
    log_success "FPGA-Agent-skills 就绪"
fi

# ══════════════════════════════════════════════════════════════════════
# Step 7: 生成 .env + activate.sh
# ══════════════════════════════════════════════════════════════════════
log_step "Step 7/8: 环境配置"

cd "${PROJECT_ROOT}"

# ── .env ──
ABC_BIN="${OSS_DIR}/bin/yosys-abc"
if [ ! -x "${ABC_BIN}" ]; then
    ABC_BIN="abc"
fi
LOGICRT_ROOT="${PROJECT_ROOT}/0reverse/GenEDA-main/reverse_engineering"
if [ ! -d "${LOGICRT_ROOT}/scripts" ]; then
    if [ -d "${PROJECT_ROOT}/../0reverse/GenEDA-main/reverse_engineering/scripts" ]; then
        LOGICRT_ROOT="$(cd "${PROJECT_ROOT}/../0reverse/GenEDA-main/reverse_engineering" && pwd)"
    elif [ -d "${PROJECT_ROOT}/../LogicRT/scripts" ]; then
        LOGICRT_ROOT="$(cd "${PROJECT_ROOT}/../LogicRT" && pwd)"
    else
        LOGICRT_ROOT=""
    fi
fi

cat > "${PROJECT_ROOT}/.env" << ENVEOF
# CktClaw 环境变量 — 由 setup.sh 自动生成 ($(date +%Y-%m-%d))

# EDA 工具路径
export PATH="${OSS_DIR}/bin:${DEPS_DIR}/opensta-install/bin:\${PATH}"

# Orchestrator 模板
export CHIP_AGENTS_ROOT="${AGENTS_DIR}/plugins"

# AI4EDA 工具
export AI4EDA_BIN="${AI4EDA_DIR}/ai4eda-toolkit"
export CKTCLAW_AI4EDA_PATH="${AI4EDA_DIR}"

# Verilog Generator + FPGA Agent Skills
export VERILOG_GENERATOR_ROOT="${VERILOG_GEN_DIR}"
export FPGA_AGENT_SKILLS_ROOT="${FPGA_SKILLS_DIR}"

# ABC 可执行文件（优先使用 oss-cad-suite 附带的 yosys-abc）
export ABC_PATH="${ABC_BIN}"

# AIG->BENCH 输出模式（gate/lut/auto）
# 默认 gate：避免部分 yosys-abc 输出 LUT BENCH 导致下游 Graph 转换丢失结构
export CKTCLAW_BENCH_FORMAT="gate"

# AI4EDA 默认 Liberty 库（ASAP7）
export AI4EDA_DEFAULT_LIB="${AI4EDA_DIR}/libs/asap7.lib"

# LogicRT 根目录（用于导入 scripts/inference_single_modal.py）
export CKTCLAW_LOGICRT_ROOT="${LOGICRT_ROOT}"

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
log_step "Step 8/8: 验证安装"

source "${PROJECT_ROOT}/.env"

# Python
PROJECT_PARENT="$(cd "${PROJECT_ROOT}/.." && pwd)"
python -c "import os,sys; os.chdir('${PROJECT_PARENT}'); from cktclaw.main import main; print('  cktclaw 模块导入 ✓')" 2>/dev/null || \
    log_warning "cktclaw 模块导入失败（请确认在 ${PROJECT_PARENT} 下可导入）"

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
        if [ "$tool" = "abc" ]; then
            if command_exists abc; then
                FOUND=$((FOUND + 1))
                log_success "abc"
            elif command_exists yosys-abc; then
                FOUND=$((FOUND + 1))
                log_success "abc (via yosys-abc)"
            else
                log_warning "abc/yosys-abc — 未检测到"
            fi
        else
            if command_exists "$tool"; then
                FOUND=$((FOUND + 1))
                log_success "$tool"
            else
                log_warning "$tool — 未检测到"
            fi
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
AI4EDA_ENTRY="${AI4EDA_DIR}/ai4eda-toolkit"
if [ -x "${AI4EDA_ENTRY}" ]; then
    log_success "AI4EDA Toolkit 可执行: ${AI4EDA_ENTRY}"
elif [ -f "${AI4EDA_ENTRY}" ]; then
    log_warning "AI4EDA Toolkit 存在但缺少执行权限，正在修复..."
    chmod +x "${AI4EDA_ENTRY}"
    log_success "AI4EDA Toolkit 权限已修复: ${AI4EDA_ENTRY}"
else
    log_warning "AI4EDA Toolkit 未找到: ${AI4EDA_ENTRY}"
fi

# LogicRT scripts
if [ -n "${LOGICRT_ROOT}" ] && [ -f "${LOGICRT_ROOT}/scripts/inference_single_modal.py" ]; then
    log_success "LogicRT scripts 可用: ${LOGICRT_ROOT}"
else
    log_warning "未检测到 LogicRT scripts 目录；请在 .env 中设置 CKTCLAW_LOGICRT_ROOT"
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
