#!/bin/bash
################################################################################
# CktClaw 一键部署脚本
#
# 功能：
# 1. 检查并创建 Conda 环境
# 2. 安装 Python 依赖
# 3. 自动配置开源 EDA 工具链（Yosys, ABC, OpenSTA）
# 4. 克隆 AI4EDA-OpenABC-Data-Toolkit
# 5. 设置环境变量
#
# 作者：CktClaw Team
# 版本：1.0.0
################################################################################

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目配置
PROJECT_NAME="cktclaw"
CONDA_ENV_NAME="cktclaw_env"
PYTHON_VERSION="3.10"
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTERNAL_TOOLS_DIR="${PROJECT_ROOT}/external_tools"

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 打印欢迎信息
print_banner() {
    cat << "EOF"
╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██████╗██╗  ██╗████████╗ ██████╗██╗      █████╗ ██╗    ██╗║
║  ██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██║     ██╔══██╗██║    ██║║
║  ██║     █████╔╝    ██║   ██║     ██║     ███████║██║ █╗ ██║║
║  ██║     ██╔═██╗    ██║   ██║     ██║     ██╔══██║██║███╗██║║
║  ╚██████╗██║  ██╗   ██║   ╚██████╗███████╗██║  ██║╚███╔███╔╝║
║   ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝ ║
║                                                              ║
║          CktClaw 一键部署脚本 v1.0.0                         ║
║          The Autonomous Multi-Agent EDA Ecosystem            ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
EOF
}

# 检查命令是否存在
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# 检查 Conda 是否安装
check_conda() {
    log_info "检查 Conda 安装..."
    if ! command_exists conda; then
        log_error "未检测到 Conda！请先安装 Miniconda 或 Anaconda"
        log_info "下载地址: https://docs.conda.io/en/latest/miniconda.html"
        exit 1
    fi
    log_success "Conda 已安装: $(conda --version)"
}

# 创建或激活 Conda 环境
setup_conda_env() {
    log_info "设置 Conda 环境..."

    # 检查环境是否已存在
    if conda env list | grep -q "^${CONDA_ENV_NAME} "; then
        log_warning "环境 ${CONDA_ENV_NAME} 已存在"
        read -p "是否删除并重新创建？(y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            log_info "删除旧环境..."
            conda env remove -n ${CONDA_ENV_NAME} -y
        else
            log_info "使用现有环境"
            return 0
        fi
    fi

    log_info "创建 Conda 环境: ${CONDA_ENV_NAME} (Python ${PYTHON_VERSION})"
    conda create -n ${CONDA_ENV_NAME} python=${PYTHON_VERSION} -y
    log_success "Conda 环境创建成功"
}

# 安装 Python 依赖
install_python_deps() {
    log_info "安装 Python 依赖..."

    # 激活环境
    eval "$(conda shell.bash hook)"
    conda activate ${CONDA_ENV_NAME}

    # 升级 pip
    pip install --upgrade pip

    # 安装核心依赖
    log_info "安装核心依赖包..."
    pip install \
        pydantic \
        rich \
        prompt_toolkit \
        aiosqlite \
        tiktoken \
        openai \
        anthropic \
        streamlit \
        plotly \
        pandas \
        numpy

    # 安装 PyTorch (CPU 版本，如需 GPU 请手动安装)
    log_info "安装 PyTorch (CPU 版本)..."
    pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

    log_success "Python 依赖安装完成"
}

# 安装 EDA 工具链
install_eda_tools() {
    log_info "安装开源 EDA 工具链..."

    eval "$(conda shell.bash hook)"
    conda activate ${CONDA_ENV_NAME}

    # 方案 1: 使用 conda-forge 安装（推荐）
    log_info "尝试通过 conda-forge 安装 EDA 工具..."

    # 安装 Yosys
    if ! command_exists yosys; then
        log_info "安装 Yosys..."
        conda install -c conda-forge yosys -y || {
            log_warning "Conda 安装 Yosys 失败，尝试使用系统包管理器..."
            install_yosys_system
        }
    else
        log_success "Yosys 已安装: $(yosys -V | head -1)"
    fi

    # 安装 ABC
    if ! command_exists abc; then
        log_info "安装 ABC..."
        # ABC 通常需要从源码编译或使用预编译二进制
        install_abc_binary
    else
        log_success "ABC 已安装"
    fi

    # 安装 OpenSTA
    if ! command_exists sta; then
        log_info "安装 OpenSTA..."
        install_opensta
    else
        log_success "OpenSTA 已安装"
    fi
}

# 使用系统包管理器安装 Yosys
install_yosys_system() {
    if command_exists apt-get; then
        log_info "使用 apt-get 安装 Yosys..."
        sudo apt-get update
        sudo apt-get install -y yosys
    elif command_exists yum; then
        log_info "使用 yum 安装 Yosys..."
        sudo yum install -y yosys
    elif command_exists brew; then
        log_info "使用 Homebrew 安装 Yosys..."
        brew install yosys
    else
        log_warning "无法自动安装 Yosys，请手动安装"
        log_info "参考: https://github.com/YosysHQ/yosys"
    fi
}

# 安装 ABC 二进制
install_abc_binary() {
    log_info "下载 ABC 预编译二进制..."

    mkdir -p ${EXTERNAL_TOOLS_DIR}/abc
    cd ${EXTERNAL_TOOLS_DIR}/abc

    # 检测操作系统
    if [[ "$OSTYPE" == "linux-gnu"* ]]; then
        ABC_URL="https://github.com/berkeley-abc/abc/releases/download/v1.01/abc-linux-x86_64"
    elif [[ "$OSTYPE" == "darwin"* ]]; then
        ABC_URL="https://github.com/berkeley-abc/abc/releases/download/v1.01/abc-macos-x86_64"
    else
        log_warning "不支持的操作系统，请手动安装 ABC"
        return 1
    fi

    wget -O abc ${ABC_URL} || curl -L -o abc ${ABC_URL}
    chmod +x abc

    # 创建符号链接
    mkdir -p ${PROJECT_ROOT}/bin
    ln -sf ${EXTERNAL_TOOLS_DIR}/abc/abc ${PROJECT_ROOT}/bin/abc

    log_success "ABC 安装完成"
}

# 安装 OpenSTA
install_opensta() {
    log_info "从源码编译 OpenSTA..."

    mkdir -p ${EXTERNAL_TOOLS_DIR}
    cd ${EXTERNAL_TOOLS_DIR}

    if [ ! -d "OpenSTA" ]; then
        git clone https://github.com/The-OpenROAD-Project/OpenSTA.git
    fi

    cd OpenSTA
    mkdir -p build
    cd build

    # 检查依赖
    if ! command_exists cmake; then
        log_error "需要 CMake 来编译 OpenSTA"
        log_info "请安装: sudo apt-get install cmake (Ubuntu) 或 brew install cmake (macOS)"
        return 1
    fi

    cmake .. -DCMAKE_INSTALL_PREFIX=${EXTERNAL_TOOLS_DIR}/OpenSTA/install
    make -j$(nproc)
    make install

    # 创建符号链接
    mkdir -p ${PROJECT_ROOT}/bin
    ln -sf ${EXTERNAL_TOOLS_DIR}/OpenSTA/install/bin/sta ${PROJECT_ROOT}/bin/sta

    log_success "OpenSTA 编译安装完成"
}

# 克隆 AI4EDA Toolkit
clone_ai4eda_toolkit() {
    log_info "克隆 AI4EDA-OpenABC-Data-Toolkit..."

    mkdir -p ${EXTERNAL_TOOLS_DIR}
    cd ${EXTERNAL_TOOLS_DIR}

    if [ -d "AI4EDA-OpenABC-Data-Toolkit" ]; then
        log_warning "AI4EDA-OpenABC-Data-Toolkit 已存在"
        read -p "是否更新到最新版本？(y/N): " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            cd AI4EDA-OpenABC-Data-Toolkit
            git pull
            log_success "AI4EDA Toolkit 更新完成"
        fi
    else
        git clone https://github.com/959AI994/AI4EDA-OpenABC-Data-Toolkit.git
        log_success "AI4EDA Toolkit 克隆完成"
    fi

    # 构建 AI4EDA Toolkit
    cd ${EXTERNAL_TOOLS_DIR}/AI4EDA-OpenABC-Data-Toolkit
    if [ -f "setup.py" ]; then
        log_info "安装 AI4EDA Toolkit..."
        pip install -e .
    fi
}

# 设置环境变量
setup_environment() {
    log_info "设置环境变量..."

    # 创建环境变量配置文件
    ENV_FILE="${PROJECT_ROOT}/.env"

    cat > ${ENV_FILE} << EOF
# CktClaw 环境变量配置
# 自动生成于: $(date)

# 项目路径
export CKTCLAW_ROOT="${PROJECT_ROOT}"
export CKTCLAW_BIN="${PROJECT_ROOT}/bin"

# EDA 工具路径
export ABC_PATH="${PROJECT_ROOT}/bin/abc"
export YOSYS_PATH="$(which yosys 2>/dev/null || echo '')"
export OPENSTA_PATH="${PROJECT_ROOT}/bin/sta"
export AI4EDA_TOOLKIT="${EXTERNAL_TOOLS_DIR}/AI4EDA-OpenABC-Data-Toolkit/ai4eda-toolkit"

# Python 路径
export PYTHONPATH="${PROJECT_ROOT}:\${PYTHONPATH}"

# 添加 bin 到 PATH
export PATH="${PROJECT_ROOT}/bin:\${PATH}"

# GPU 配置（如果需要）
# export CUDA_VISIBLE_DEVICES="0,1,2,3"

# DeepSeek API 配置（可选）
# export DEEPSEEK_API_KEY="your-api-key-here"
EOF

    log_success "环境变量配置文件已创建: ${ENV_FILE}"

    # 创建激活脚本
    ACTIVATE_SCRIPT="${PROJECT_ROOT}/activate.sh"

    cat > ${ACTIVATE_SCRIPT} << 'EOF'
#!/bin/bash
# CktClaw 环境激活脚本

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 激活 Conda 环境
eval "$(conda shell.bash hook)"
conda activate cktclaw_env

# 加载环境变量
source ${PROJECT_ROOT}/.env

echo "✓ CktClaw 环境已激活"
echo "  Python: $(which python)"
echo "  项目路径: ${CKTCLAW_ROOT}"
echo ""
echo "运行 CktClaw:"
echo "  python -m cktclaw"
echo ""
echo "或直接运行:"
echo "  cktclaw"
EOF

    chmod +x ${ACTIVATE_SCRIPT}
    log_success "激活脚本已创建: ${ACTIVATE_SCRIPT}"
}

# 创建启动脚本
create_launcher() {
    log_info "创建启动脚本..."

    LAUNCHER="${PROJECT_ROOT}/bin/cktclaw"
    mkdir -p ${PROJECT_ROOT}/bin

    cat > ${LAUNCHER} << 'EOF'
#!/bin/bash
# CktClaw 启动脚本

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# 激活环境
source ${PROJECT_ROOT}/activate.sh

# 启动 CktClaw
cd ${PROJECT_ROOT}
python -m cktclaw "$@"
EOF

    chmod +x ${LAUNCHER}
    log_success "启动脚本已创建: ${LAUNCHER}"
}

# 运行测试
run_tests() {
    log_info "运行基础测试..."

    eval "$(conda shell.bash hook)"
    conda activate ${CONDA_ENV_NAME}
    source ${PROJECT_ROOT}/.env

    # 测试 Python 导入
    python -c "
import sys
sys.path.insert(0, '${PROJECT_ROOT}')
from harness import get_state_manager, get_task_manager, get_skill_registry
from cktmem import Storage, ContextManager
print('✓ 核心模块导入成功')
" || {
        log_error "Python 模块导入测试失败"
        return 1
    }

    # 测试 EDA 工具
    if command_exists yosys; then
        log_success "Yosys 可用: $(yosys -V | head -1)"
    else
        log_warning "Yosys 未安装或不在 PATH 中"
    fi

    if [ -f "${PROJECT_ROOT}/bin/abc" ]; then
        log_success "ABC 可用"
    else
        log_warning "ABC 未安装"
    fi

    log_success "基础测试完成"
}

# 打印完成信息
print_completion() {
    cat << EOF

╔══════════════════════════════════════════════════════════════╗
║                    🎉 安装完成！                             ║
╚══════════════════════════════════════════════════════════════╝

下一步操作：

1. 激活 CktClaw 环境：
   $ source activate.sh

2. 启动 CktClaw：
   $ cktclaw

   或者：
   $ python -m cktclaw

3. 查看帮助：
   $ cktclaw --help

4. 启动性能监控面板：
   $ streamlit run cktclaw/ui/dashboard.py

环境变量配置文件：
  ${PROJECT_ROOT}/.env

如遇问题，请查看：
  - 文档: ${PROJECT_ROOT}/README.md
  - Issues: https://github.com/your-org/cktclaw/issues

EOF
}

# 主函数
main() {
    print_banner

    log_info "开始安装 CktClaw..."
    log_info "项目路径: ${PROJECT_ROOT}"

    # 执行安装步骤
    check_conda
    setup_conda_env
    install_python_deps
    install_eda_tools
    clone_ai4eda_toolkit
    setup_environment
    create_launcher
    run_tests

    print_completion

    log_success "CktClaw 安装完成！"
}

# 运行主函数
main "$@"
