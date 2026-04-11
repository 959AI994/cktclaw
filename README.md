<div align="center">

<img src="figure/cktclaw2(1).png" alt="CktClaw logo" width="100%" />

# CktClaw

**面向智能 EDA 的多智能体自主生态 · The Autonomous Multi-Agent Ecosystem for Intelligent EDA**

[Jingxin Wang](https://github.com/959AI994) · PhD Student · Shanghai Jiao Tong University · ACE Lab

</div>

---

**CktClaw** 专注于 AIG→Verilog 功能恢复与 AI4EDA 数据编排：在图神经网络与大模型辅助下，将门级抽象还原为结构化 RTL，并串联分析、综合与度量工具链。

---

## Contents

| [Key Capabilities](#key-capabilities) | [Features](#features) | [Installation](#installation) |
| :---: | :---: | :---: |
| [Quick Start](#quick-start) | [Commands](#available-commands) | [Architecture](#architecture) |
| [Models](#models) | [Use Cases](#use-cases) | [Configuration](#configuration) |
| [Troubleshooting](#troubleshooting) | [Citation](#citation) | [Contact](#contact) |

---

## Key Capabilities

*核心能力：AIG 逆向、数据工具链与综合度量*

- **Circuit Reverse Engineering**: 面向 AIG→Verilog 的语义恢复与结构模式识别，支持复杂控制/数据通路重建与净化。
- **AI4EDA Hub**: 内置 GraphML/PyG 转换与向量化表征，结合大模型实现可解释电路理解与知识注入。
- **Hardware Metrics & Synthesis**: 集成 ABC/Yosys，基于 ASAP7 库进行面积/时延估计，并支持自动化优化序列探索。
- **High-Performance Data Tooling**: 面向大规模数据集的高吞吐转换与清洗，覆盖跨版本 PyG 兼容性与稳健 I/O。

---

## Features

*功能概览：交互式 CLI、多引擎与 EDA 集成*

### 1. Interactive CLI Interface
- Modern REPL experience with command history and auto-completion
- Rich terminal UI with syntax highlighting and progress indicators
- Session management with SQLite persistence

### 2. Multi-Engine Support
- **LogicRT**: Local inference engine based on CodeV model (default)
- **DeepSeek**: Cloud-based API for enhanced analysis
- Dynamic engine switching at runtime

### 3. Integrated EDA Tools
- **ABC**: Advanced logic synthesis and optimization
- **Yosys**: Open-source synthesis framework
- **OpenSTA**: Static timing analysis tool
- Interactive terminals for all tools

### 4. AI4EDA Toolkit
- AIG/AIGER format conversion
- PyTorch Geometric (PyG) data processing
- GraphML generation and manipulation
- Batch processing for large datasets

### 5. Circuit Analysis Pipeline
```
AIG File → PT Format → LogicRT Inference → Verilog Generation
         ↓
    Syntax Validation → LLM Analysis → Session Storage
```

---

## Installation

### Prerequisites
- Python 3.10+
- Conda environment manager
- CUDA-capable GPU (optional, for local inference)

### Setup
```bash
# Clone the repository
git clone git@github.com:959AI994/cktclaw.git
cd cktclaw

# Create and activate conda environment
conda create -n aig_verilog python=3.10
conda activate aig_verilog

# Install dependencies
pip install -r requirements.txt  # if available
# or install manually:
pip install prompt_toolkit rich torch transformers
```

---

## Quick Start

### Launch CktClaw
```bash
cd /path/to/cktclaw
conda activate aig_verilog
python -m cktclaw.main
```

You'll see the welcome screen:
```
██████╗██╗  ██╗████████╗ ██████╗██╗      █████╗ ██╗    ██╗
██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██║     ██╔══██╗██║    ██║
██║     █████╔╝    ██║   ██║     ██║     ███████║██║ █╗ ██║
██║     ██╔═██╗    ██║   ██║     ██║     ██╔══██║██║███╗██║
╚██████╗██║  ██╗   ██║   ╚██████╗███████╗██║  ██║╚███╔███╔╝
 ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA
```

---

## Available Commands

### Circuit Reverse Engineering
```bash
/reverse <path>    # Convert AIG to Verilog and analyze
```

### EDA Tool Integration
```bash
/abc               # Launch interactive ABC terminal
/yosys             # Launch interactive Yosys terminal
/opensta           # Launch interactive OpenSTA terminal
```

### AI4EDA Toolkit
```bash
/ai4eda            # Enter AI4EDA data processing toolkit
```

### Model Management
```bash
/model             # Interactive model selection (LogicRT/DeepSeek)
/engine <name>     # Switch analysis engine
```

### Session Management
```bash
/clear             # Start new session
/session info      # Show current session details
/sessions list     # List recent sessions
```

### Help & Exit
```bash
/help              # Show all commands
Ctrl+C             # Exit CktClaw
```

---

## Architecture

```
cktclaw/
├── main.py                    # REPL main loop
├── config.py                  # Configuration settings
├── handlers/                  # Command handlers
│   ├── reverse_handler.py     # AIG→Verilog reverse engineering
│   ├── abc_handler.py         # ABC tool integration
│   ├── yosys_handler.py       # Yosys tool integration
│   ├── ai4eda_handler.py      # AI4EDA toolkit
│   ├── model_handler.py       # Model selection
│   ├── engine_handler.py      # Engine switching
│   ├── session_handler.py     # Session management
│   └── help_handler.py        # Help system
├── eda_tools/                 # EDA tool runners
│   ├── abc_runner.py          # ABC wrapper
│   ├── yosys_runner.py        # Yosys wrapper
│   └── tool_dicts.py          # Tool configurations
├── ui/                        # User interface
│   ├── colors.py              # Color schemes
│   └── renderer.py            # Rich components
└── utils/                     # Utilities
    └── completers.py          # Auto-completion
```

---

## Models

CktClaw integrates multiple AI models for circuit analysis:

- **LogicRT**: A specialized model for AIG-to-Verilog conversion, trained on circuit datasets
- **CodeV**: Local LLM for code analysis and generation
- **DeepSeek**: Cloud-based API for enhanced reasoning

LogicRT is the core model that powers the reverse engineering pipeline, while CodeV and DeepSeek provide natural language analysis capabilities.

---

## Use Cases

### 1. Circuit Reverse Engineering
Convert AIG files to readable Verilog HDL:
```bash
> /reverse test/aig/adder.aig
```

### 2. Logic Synthesis Exploration
Experiment with ABC optimization sequences:
```bash
> /abc
abc> read_aiger circuit.aig
abc> strash; balance; rewrite
```

### 3. AI4EDA Data Processing
Batch convert AIG files for ML training:
```bash
> /ai4eda
[AI4EDA Toolkit Menu]
```

### 4. Interactive Circuit Analysis
Ask questions about generated Verilog:
```bash
> /reverse circuit.aig
> What is the function of this circuit?
> Can you optimize the critical path?
```

---

## Configuration

Edit `config.py` to customize:
- Default analysis engine
- GPU device allocation
- Model paths
- Database location
- UI themes

---

## Performance Tips

1. **GPU Isolation**: Set `CUDA_VISIBLE_DEVICES` to avoid conflicts
2. **Model Loading**: First-time model loading may take 30-60 seconds
3. **Session Persistence**: All sessions are automatically saved to SQLite

---

## Troubleshooting

**Issue**: Module not found errors
```bash
conda activate aig_verilog
pip install prompt_toolkit rich
```

**Issue**: GPU out of memory
- Switch to DeepSeek engine (cloud-based)
- Reduce batch size for AI4EDA operations
- Check other GPU processes

**Issue**: ABC/Yosys not found
- Set `ABC_PATH` and `YOSYS_PATH` environment variables
- Or install tools to system PATH

---

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

---

## License

[Add your license here]

---

## Citation

If you use CktClaw in your research, please cite:

```bibtex
@software{cktclaw2024,
  author = {Wang, Jingxin},
  title = {CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA},
  year = {2024},
  institution = {Shanghai Jiao Tong University}
}
```

---

## Contact

- **Author**: Jingxin Wang
- **Institution**: Shanghai Jiao Tong University
- **Lab**: ACE Lab

---

**Note**: LogicRT is one of the AI models integrated into CktClaw for AIG-to-Verilog conversion. CktClaw is the complete ecosystem that includes LogicRT along with other tools and capabilities.
