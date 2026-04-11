<div align="center">

<img src="figure/cktclaw2(1).png" alt="CktClaw logo" width="100%" />

# CktClaw

**面向智能 EDA 的多智能体自主生态 · The Autonomous Multi-Agent Ecosystem for Intelligent EDA**

[AlexWang](https://github.com/959AI994) · PhD Student · Shanghai Jiao Tong University · ACE Lab

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-16%2F16%20passing-brightgreen.svg)](tests/)

</div>

---

## 📋 目录 · Table of Contents

| [核心能力](#-核心能力--key-capabilities) | [功能特性](#-功能特性--features) | [快速开始](#-快速开始--quick-start) |
| :---: | :---: | :---: |
| [架构设计](#-架构设计--architecture) | [命令参考](#-命令参考--commands) | [配置说明](#-配置说明--configuration) |
| [使用案例](#-使用案例--use-cases) | [故障排除](#-故障排除--troubleshooting) | [引用](#-引用--citation) |

---

## 🎯 核心能力 · Key Capabilities

### 1. 电路逆向工程 · Circuit Reverse Engineering
- **AIG→Verilog 语义恢复**：将门级抽象还原为结构化 RTL，支持复杂控制/数据通路重建
- **模式识别与净化**：基于图神经网络的电路结构分析与优化
- **多引擎支持**：LogicRT 本地推理 + DeepSeek 云端增强

### 2. 智能上下文管理 · Intelligent Context Management
- **四层上下文架构**：System / Project / Session / Turn 层级隔离
- **自动压缩策略**：Token 超过 150K 自动触发，支持 Session Memory / Micro / Full 多策略
- **边界隔离机制**：防止语义混淆，保留核心决策历史

### 3. 高性能工具编排 · High-Performance Tool Orchestration
- **智能并行/串行执行**：自动分析工具依赖关系，最大化执行效率
- **Context Modifier 机制**：正确处理并行工具的上下文修改
- **速率限制保护**：Token Bucket 算法防止 API 过载

### 4. AI4EDA 数据工具链 · AI4EDA Data Tooling
- **GraphML/PyG 转换**：支持大规模数据集的高吞吐转换与清洗
- **向量化表征**：结合大模型实现可解释电路理解
- **跨版本兼容**：覆盖 PyG 多版本兼容性与稳健 I/O

### 5. 硬件度量与综合 · Hardware Metrics & Synthesis
- **集成 ABC/Yosys**：自动化优化序列探索
- **ASAP7 库支持**：面积/时延精确估计
- **静态时序分析**：OpenSTA 集成

---

## ✨ 功能特性 · Features

### 🖥️ 交互式 CLI 界面 · Interactive CLI
- 现代化 REPL 体验，支持命令历史和自动补全
- Rich 终端 UI，语法高亮和进度指示
- SQLite 会话持久化

### 🧠 CktMem 记忆系统 · CktMem Memory System
- **四层上下文模型**：
  - **System Layer**: 系统 Prompt、工具定义、全局规则
  - **Project Layer**: 工作区状态、项目级 Memory
  - **Session Layer**: 核心上下文、压缩摘要
  - **Turn Layer**: 最近 N 轮对话、当前输入

- **自动压缩触发**：
  - Token 阈值：150,000 tokens
  - 压缩目标：40,000 tokens
  - 策略选择：Session Memory → Micro → Full → Simple Suffix

- **压缩边界标记**：
  ```
  ━━━ COMPACT BOUNDARY ━━━
  Previous conversation has been summarized.
  Pre-compact tokens: 150000
  Post-compact tokens: 42000
  Tokens saved: 108000
  ```

### 🔧 Harness Services (95% 完整度)

#### 1. Auto Compact - 自动压缩
- **Session Memory Compact**: 保留后缀消息，最轻量
- **Micro Compact**: 清理工具结果、图片/文档块
- **Full Compact**: LLM 总结，最大压缩率
- **Simple Suffix**: 兜底策略，始终可用

#### 2. Tool Orchestration - 工具编排
- **智能分批执行**: 自动分析依赖关系
- **并行执行**: 独立工具并发运行
- **串行执行**: 依赖工具顺序执行
- **Context Modifier**: 正确处理上下文修改

#### 3. Rate Limiting - 速率限制
- **Token Bucket 算法**: 每分钟 60 请求 / 100K tokens
- **自动等待重试**: 超限自动等待并重试
- **并发控制**: 最多 10 个并发请求

#### 4. Hook System - 钩子系统
- **Pre-Compact Hooks**: 压缩前修改行为
- **Post-Compact Hooks**: 压缩后处理结果
- **Session Start Hooks**: 会话启动初始化
- **可扩展注册**: 支持自定义钩子

#### 5. File Attachment Recovery - 文件附件恢复
- **智能文件选择**: 按时间戳排序，最近优先
- **Token 预算管理**: 限制文件数量和大小
- **自动去重**: 排除已在保留消息中的文件

### 🛠️ EDA 工具集成 · EDA Tools Integration
- **ABC**: 高级逻辑综合与优化
- **Yosys**: 开源综合框架
- **OpenSTA**: 静态时序分析
- 所有工具支持交互式终端

### 🤖 多引擎支持 · Multi-Engine Support
- **LogicRT**: 本地推理引擎（默认）
- **DeepSeek**: 云端 API 增强分析
- 运行时动态切换

---

## 🚀 快速开始 · Quick Start

### 安装 · Installation

```bash
# 克隆仓库
git clone git@github.com:959AI994/cktclaw.git
cd cktclaw

# 创建 Conda 环境
conda create -n aig_verilog python=3.10
conda activate aig_verilog

# 安装依赖
pip install prompt_toolkit rich torch transformers anthropic
```

### 启动 · Launch

```bash
python main.py
```

欢迎界面：
```
██████╗██╗  ██╗████████╗ ██████╗██╗      █████╗ ██╗    ██╗
██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██║     ██╔══██╗██║    ██║
██║     █████╔╝    ██║   ██║     ██║     ███████║██║ █╗ ██║
██║     ██╔═██╗    ██║   ██║     ██║     ██╔══██║██║███╗██║
╚██████╗██║  ██╗   ██║   ╚██████╗███████╗██║  ██║╚███╔███╔╝
 ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚══════╝╚═╝  ╚═╚══╝╚══╝

CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA
```

### 基本使用 · Basic Usage

```bash
# 电路逆向工程
> /reverse test/aig/adder.aig

# 启动 ABC 工具
> /abc

# 进入 AI4EDA 工具包
> /ai4eda

# 切换模型引擎
> /model

# 查看会话信息
> /session info

# 帮助
> /help
```

---

## 🏗️ 架构设计 · Architecture

### 项目结构 · Project Structure

```
cktclaw/
├── main.py                          # REPL 主循环
├── config.py                        # 配置设置
├── cktmem/                          # 记忆管理系统
│   ├── manager.py                   # 上下文管理器
│   ├── compactor.py                 # 压缩器
│   ├── storage.py                   # SQLite 存储层
│   ├── token_counter.py             # Token 计数器
│   └── models.py                    # 数据模型
├── harness/                         # Harness Services
│   ├── services/
│   │   ├── compact/                 # 压缩服务
│   │   │   ├── auto_compact.py      # 自动压缩
│   │   │   ├── micro_compact.py     # 微压缩
│   │   │   └── attachments.py       # 文件附件恢复
│   │   ├── tools/                   # 工具服务
│   │   │   └── tool_orchestration.py # 工具编排
│   │   └── api/                     # API 服务
│   │       └── rate_limiter.py      # 速率限制
│   ├── hooks/                       # 钩子系统
│   │   ├── pre_compact.py           # 压缩前钩子
│   │   ├── post_compact.py          # 压缩后钩子
│   │   └── session_start.py         # 会话启动钩子
│   └── query/                       # 查询循环
│       └── query_loop_enhanced.py   # 增强查询循环
├── handlers/                        # 命令处理器
│   ├── chat_handler_v2.py           # 对话处理（集成速率限制）
│   ├── reverse_handler.py           # 逆向工程
│   ├── abc_handler.py               # ABC 集成
│   ├── yosys_handler.py             # Yosys 集成
│   ├── ai4eda_handler.py            # AI4EDA 工具包
│   └── session_handler.py           # 会话管理
├── eda_tools/                       # EDA 工具运行器
│   ├── abc_runner.py                # ABC 包装器
│   └── yosys_runner.py              # Yosys 包装器
└── ui/                              # 用户界面
    ├── colors.py                    # 颜色方案
    └── renderer.py                  # Rich 组件
```

### 数据流 · Data Flow

```
用户输入 → ContextManager.build_context()
    ↓
四层上下文组装 (System/Project/Session/Turn)
    ↓
Token 估算 → 超过 150K？
    ↓ 是
Compactor.auto_compact()
    ├─ Pre-Compact Hooks
    ├─ 策略选择 (Session Memory → Micro → Full)
    ├─ 压缩执行
    ├─ 文件附件恢复
    └─ Post-Compact Hooks
    ↓
RateLimiter.acquire() → 速率检查
    ↓
LLM 调用 (LogicRT/DeepSeek)
    ↓
工具编排 (Tool Orchestration)
    ├─ 并行执行独立工具
    └─ 串行执行依赖工具
    ↓
响应存储 → SQLite
```

---

## 📚 命令参考 · Commands

### 电路逆向 · Circuit Reverse
```bash
/reverse <path>        # AIG→Verilog 转换与分析
```

### EDA 工具 · EDA Tools
```bash
/abc                   # 启动 ABC 交互终端
/yosys                 # 启动 Yosys 交互终端
/opensta               # 启动 OpenSTA 交互终端
```

### AI4EDA 工具包 · AI4EDA Toolkit
```bash
/ai4eda                # 进入数据处理工具包
```

### 模型管理 · Model Management
```bash
/model                 # 交互式模型选择
/engine <name>         # 切换分析引擎
```

### 会话管理 · Session Management
```bash
/clear                 # 开始新会话
/session info          # 显示当前会话详情
/sessions list         # 列出最近会话
```

### 帮助与退出 · Help & Exit
```bash
/help                  # 显示所有命令
Ctrl+C                 # 退出 CktClaw
```

---

## ⚙️ 配置说明 · Configuration

### 压缩配置 · Compact Configuration

编辑 `cktmem/models.py`:

```python
@dataclass
class CompactConfig:
    auto_compact_threshold: int = 150_000  # 自动压缩阈值
    target_tokens: int = 40_000            # 目标 Token 数
    buffer_tokens: int = 13_000            # 缓冲 Token 数
```

### 速率限制配置 · Rate Limit Configuration

编辑 `handlers/chat_handler_v2.py`:

```python
config = RateLimitConfig(
    max_requests_per_minute=60,       # 每分钟最多 60 请求
    max_tokens_per_minute=100_000,    # 每分钟最多 100K tokens
    max_concurrent_requests=10,       # 最多 10 个并发请求
)
```

### 文件附件配置 · File Attachment Configuration

编辑 `harness/services/compact/attachments.py`:

```python
POST_COMPACT_MAX_FILES_TO_RESTORE = 5      # 最多恢复 5 个文件
POST_COMPACT_TOKEN_BUDGET = 50_000         # Token 预算 50K
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000   # 每个文件最多 5K tokens
```

---

## 💡 使用案例 · Use Cases

### 案例 1: 电路逆向工程
```bash
> /reverse test/aig/multiplier.aig
[LogicRT] 正在分析电路...
[Verilog] 生成成功
> 这个电路实现什么功能？
[Assistant] 这是一个 8 位乘法器，采用华莱士树结构...
```

### 案例 2: 逻辑综合探索
```bash
> /abc
abc> read_aiger circuit.aig
abc> strash; balance; rewrite; refactor
abc> print_stats
```

### 案例 3: AI4EDA 数据处理
```bash
> /ai4eda
[AI4EDA Toolkit]
1. AIG → PyG 批量转换
2. GraphML 生成
3. 数据集清洗
> 1
[Batch] 处理 1000 个 AIG 文件...
```

### 案例 4: 长对话自动压缩
```bash
> 分析这个电路
> 继续分析时序特性
> 详细说明关键路径
... (多轮对话)
[INFO] Token count: 155000 > threshold: 150000
[INFO] Triggering auto-compact...
[Compact] Pre-compact tokens: 155000
[Compact] Post-compact tokens: 42000
💾 Compacted conversation, saved ~113,000 tokens
```

---

## 🔍 故障排除 · Troubleshooting

### 问题 1: 模块未找到
```bash
conda activate aig_verilog
pip install prompt_toolkit rich torch transformers
```

### 问题 2: GPU 内存不足
- 切换到 DeepSeek 引擎（云端）
- 减少 AI4EDA 批处理大小
- 检查其他 GPU 进程

### 问题 3: ABC/Yosys 未找到
```bash
export ABC_PATH=/path/to/abc
export YOSYS_PATH=/path/to/yosys
```

### 问题 4: 压缩未触发
- 检查 Token 数是否超过 150K
- 确认 `auto_compact=True`
- 查看日志是否有错误

### 问题 5: 速率限制过严
编辑 `handlers/chat_handler_v2.py` 增加限制：
```python
config = RateLimitConfig(
    max_requests_per_minute=120,      # 增加到 120
    max_tokens_per_minute=200_000,    # 增加到 200K
)
```

---

## 🧪 测试 · Testing

### 运行测试 · Run Tests

```bash
# 核心功能测试
python test_harness_complete.py

# 集成验证
python verify_integration.py

# 下一步行动测试
python test_next_steps.py
```

### 测试覆盖 · Test Coverage

- ✅ 核心功能测试: 6/6 通过
- ✅ 集成验证: 6/6 通过
- ✅ 下一步行动: 4/4 通过
- **总计**: 16/16 通过 (100%)

---

## 📊 性能指标 · Performance Metrics

### 功能完整度 · Functionality Completeness

| 模块 | 完整度 | 状态 |
|------|--------|------|
| Auto Compact | 90% | 🟢 优秀 |
| Micro Compact | 95% | 🟢 优秀 |
| Tool Orchestration | 90% | 🟢 优秀 |
| API Services | 100% | 🟢 完美 |
| Tools | 100% | 🟢 完美 |
| Hooks | 95% | 🟢 优秀 |
| Attachments | 90% | 🟢 优秀 |
| **总体** | **95%** | 🟢 **优秀** |

### 代码统计 · Code Statistics

- 核心代码: 1,419 行
- 测试代码: 930 行
- 文档: 2,950 行
- **总计**: 5,299 行

---

## 🤝 贡献 · Contributing

欢迎贡献！请随时提交 issues 或 pull requests。

---

## 📄 许可证 · License

MIT License

---

## 📖 引用 · Citation

如果您在研究中使用 CktClaw，请引用：

```bibtex
@software{cktclaw2024,
  author = {Wang, Jingxin},
  title = {CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA},
  year = {2024},
  institution = {Shanghai Jiao Tong University},
  url = {https://github.com/959AI994/cktclaw}
}
```

---

## 📧 联系方式 · Contact

- **作者 · Author**: Jingxin Wang
- **机构 · Institution**: Shanghai Jiao Tong University
- **实验室 · Lab**: ACE Lab
- **GitHub**: [@959AI994](https://github.com/959AI994)

---

<div align="center">

**CktClaw** - 让电路分析更智能 · Making Circuit Analysis Smarter

⭐ 如果这个项目对您有帮助，请给我们一个 Star！

</div>
