<div align="center">

<img src="figure/cktclaw2(1).png" alt="CktClaw logo" width="100%" />

# CktClaw

**The Autonomous Multi-Agent Ecosystem for Intelligent EDA**

[AlexWang](https://github.com/959AI994) · PhD Student · Shanghai Jiao Tong University · ACE Lab

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)](tests/)

[中文文档](README-CN.md) | **English**

</div>

---

## 🎯 CktClaw

CktClaw is a **multi-agent AI terminal for chip design**. Describe your task in natural language, and CktClaw automatically identifies the design domain, orchestrates EDA tools, drives multi-stage workflows, and delivers complete analysis results.

**Highlights:**

- **Natural-language chip design** — Type "synthesize this adder targeting minimum area" and CktClaw auto-routes to the synthesis orchestrator, executing constraint → compile → QC → sign-off stages
- **14 chip design domains** — Architecture / RTL / Verification / Formal / Synthesis / DFT / STA / HLS / Physical Design / SoC / Compiler / Firmware / FPGA / Infrastructure
- **20+ EDA tools auto-detected** — Scans Yosys, Verilator, OpenSTA, NextPNR, etc. at startup and configures MCP servers automatically
- **Intelligent context management** — 4-layer memory + automatic compression keeps critical info across long sessions
- **Circuit reverse engineering** — AIG → Verilog semantic recovery with AI-powered Q&A
- **Multi-engine support** — Local LogicRT + Cloud DeepSeek, switchable at runtime
---

<img src="figure/cktclaw_view.png" alt="CktClaw cli" width="100%" />

## 🚀 Quick Start

### Option 1: pip install (recommended)

```bash
git clone git@github.com:959AI994/cktclaw.git
cd cktclaw

conda create -n cktclaw python=3.10 -y
conda activate cktclaw

# Basic install (cloud DeepSeek engine)
pip install -e .

# Full install (includes local LogicRT engine)
pip install -e ".[full]"
```

### Option 2: Docker (batteries included)

The image ships with Yosys, ABC, Verilator, OpenSTA, SymbiYosys, nextpnr, AI4EDA Toolkit, and all 14-domain orchestrators pre-installed.

```bash
# Build from source (first build ~20-30 min, cached afterwards)
git clone git@github.com:959AI994/cktclaw.git && cd cktclaw
docker build -t cktclaw .

# Launch (pass your DeepSeek API key)
docker run -it --rm -e DEEPSEEK_API_KEY="sk-xxx" cktclaw

# Mount local design files into the container
docker run -it --rm \
  -e DEEPSEEK_API_KEY="sk-xxx" \
  -v $(pwd)/designs:/workspace \
  cktclaw
```

Or use Docker Compose:

```bash
# Set DEEPSEEK_API_KEY=sk-xxx in a .env file
docker compose up
```

### Option 3: One-Click Script (auto-installs EDA tools + dependencies)

```bash
git clone git@github.com:959AI994/cktclaw.git && cd cktclaw
bash setup.sh            # Full install (Yosys/ABC/Verilator/OpenSTA etc.)
bash setup.sh --minimal  # Python deps only, skip EDA tools
```

The script handles: Conda env → `pip install -e .` → download oss-cad-suite → build OpenSTA → clone digital-chip-design-agents + AI4EDA Toolkit → generate `.env` + `activate.sh`.

### Launch

```bash
source activate.sh  # Activate env (first time; can skip afterwards)
cktclaw
```

```
██████╗██╗  ██╗████████╗ ██████╗██╗      █████╗ ██╗    ██╗
██╔════╝██║ ██╔╝╚══██╔══╝██╔════╝██║     ██╔══██╗██║    ██║
██║     █████╔╝    ██║   ██║     ██║     ███████║██║ █╗ ██║
██║     ██╔═██╗    ██║   ██║     ██║     ██╔══██║██║███╗██║
╚██████╗██║  ██╗   ██║   ╚██████╗███████╗██║  ██║╚███╔███╔╝
 ╚═════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝╚══════╝╚═╝  ╚═╝ ╚══╝╚══╝

CktClaw > _
```

---

## 📖 Usage

### Natural Language Interaction (Most Common)

Just type your task in plain English (or Chinese). CktClaw **auto-detects** the design domain:

```bash
CktClaw > synthesize a 4-bit adder with Yosys, minimize area
→ Auto-routed to chip-synthesis

╭── Orchestrator Started ──────────────────────────────────────╮
│ synthesis-orchestrator                                        │
│ Stages: constraint_setup → compile_explore → compile_final    │
│         → netlist_qc → synthesis_signoff                      │
╰──────────────────────────────────────────────────────────────╯

━━━ Stage: constraint_setup (1/5) ━━━
  ... (AI executes automatically)

━━━ Stage: compile_explore (2/5) ━━━
  ╭── compile_explore → PASS ──╮
  │ QoR: area_cells=20         │
  │       unmapped_cells=0     │
  │       logic_levels=4       │
  ╰────────────────────────────╯

  ... (remaining stages auto-advance)

╭── Orchestrator Summary ──────────────────────────────────────╮
│ synthesis-orchestrator — 5/5 stages passed                    │
╰──────────────────────────────────────────────────────────────╯
```

More examples:

```bash
CktClaw > build a UVM testbench for my FIFO module
→ Auto-routed to chip-verification (8-stage orchestrator)

CktClaw > run timing analysis on my design, check multi-corner
→ Auto-routed to chip-sta

CktClaw > write an AXI slave RTL module
→ Auto-routed to chip-rtl

CktClaw > do formal verification using SymbiYosys
→ Auto-routed to chip-formal
```

### Circuit Reverse Engineering

```bash
CktClaw > /reverse circuits/alu.aig
[LogicRT] Analyzing circuit structure...
[Verilog] Generated: alu.v

CktClaw > What does this circuit do?
[Assistant] This is an ALU with carry-select architecture...

CktClaw > Can you suggest area optimizations?
[Assistant] Based on the analysis, the carry chain can be...
```

### EDA Tool Terminals

```bash
CktClaw > /abc                    # ABC interactive terminal
abc> read_aiger circuit.aig
abc> strash; balance; rewrite
abc> print_stats

CktClaw > /yosys                  # Yosys interactive terminal
yosys> read_verilog design.v
yosys> synth -top main

CktClaw > /opensta                # OpenSTA interactive terminal
```

### AI4EDA Data Toolkit

```bash
CktClaw > /ai4eda
╔═══════════════════════════════╗
║     AI4EDA Toolkit Menu       ║
╠═══════════════════════════════╣
║ 1. AIG → PyG batch convert    ║
║ 2. GraphML generation         ║
║ 3. Dataset cleaning           ║
║ 4. Feature extraction         ║
╚═══════════════════════════════╝
```

### Innovation Workflows

```bash
CktClaw > /rltf circuit.aig 50    # RLTF reinforcement learning synthesis
CktClaw > /pareto circuit.aig 10  # Pareto multi-agent PPA negotiation
```

---

## 📚 Command Reference

| Command | Description |
|---------|-------------|
| *(natural language)* | Auto-detect chip design task, enter matching orchestrator |
| `/reverse <path>` | AIG → Verilog reverse engineering |
| `/abc` | ABC logic synthesis terminal |
| `/yosys` | Yosys synthesis terminal |
| `/opensta` | OpenSTA timing analysis terminal |
| `/ai4eda` | AI4EDA data processing toolkit |
| `/rltf [aig] [iter]` | RLTF reinforcement learning optimization |
| `/pareto [aig] [rounds]` | Pareto multi-agent PPA negotiation |
| `/chip-design-skills` | Manually browse 14 chip design domains |
| `/model` | Switch AI engine (LogicRT / DeepSeek) |
| `/session info` | View current session |
| `/clear` | New session |
| `/help` | Full help |

---

## 🔗 14 Chip Design Domains

CktClaw covers the full chip design flow. Each domain has its own multi-stage orchestrator:

| Domain | Example Keywords | Stages |
|--------|-----------------|--------|
| **Architecture** | microarchitecture, PPA estimation | 6 stages |
| **RTL Design** | Verilog module, lint, CDC | 6 stages |
| **Verification** | UVM, testbench, coverage | 8 stages |
| **Formal** | FPV, LEC, SymbiYosys | 6 stages |
| **Synthesis** | synthesis, Yosys, netlist | 5 stages |
| **DFT** | scan chain, ATPG, JTAG | 6 stages |
| **STA** | timing, OpenSTA, multi-corner | 6 stages |
| **HLS** | C++ to RTL, Bambu | 6 stages |
| **Physical Design** | floorplan, placement, routing | 8 stages |
| **SoC** | IP integration, AXI interconnect | 6 stages |
| **Compiler** | LLVM backend, custom ISA | 7 stages |
| **Firmware** | BSP, driver, RTOS | 6 stages |
| **FPGA** | bitstream, NextPNR | 6 stages |
| **Infrastructure** | tool detection, wrapper deploy | 5 stages |

Each stage is LLM-driven. On failure, the orchestrator auto-loops back per configurable rules and escalates when the retry limit is reached.

---

## ⚙️ Configuration

### DeepSeek Cloud Engine (default)

```bash
export DEEPSEEK_API_KEY="your-api-key"
```

Or switch engines inside CktClaw:

```bash
CktClaw > /model
```

### EDA Tools

CktClaw **auto-detects** installed EDA tools at startup (Yosys, Verilator, OpenSTA, ABC, NextPNR, etc.). No manual configuration needed.

To install the open-source EDA suite:

```bash
# oss-cad-suite (one-line install: Yosys + Verilator + NextPNR + SymbiYosys ...)
wget https://github.com/YosysHQ/oss-cad-suite-build/releases/download/...
tar xzf oss-cad-suite-*.tgz
export PATH="$PWD/oss-cad-suite/bin:$PATH"
```

---

## 📖 Citation

If you use CktClaw in your research, please cite:

```bibtex
@software{cktclaw2026,
  author = {Wang, Jingxin},
  title = {CktClaw: The Autonomous Multi-Agent Ecosystem for Intelligent EDA},
  year = {2026},
  institution = {Shanghai Jiao Tong University},
  url = {https://github.com/959AI994/cktclaw}
}
```

---

## 🤝 Contributing

Contributions welcome! Please submit [Issues](https://github.com/959AI994/cktclaw/issues) or Pull Requests.

## 📄 License

MIT License

## 📧 Contact

- **Author**: Jingxin Wang · Shanghai Jiao Tong University
- **Email**: jingxin.wang@sjtu.edu.cn
- **GitHub**: [@959AI994](https://github.com/959AI994)

---

<div align="center">

**CktClaw** — Making Chip Design Smarter

⭐ Star us on GitHub if this project helps you!

[Report Bug](https://github.com/959AI994/cktclaw/issues) · [Request Feature](https://github.com/959AI994/cktclaw/issues) · [English Docs](README-EN.md)

</div>
