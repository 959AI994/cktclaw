<div align="center">

<img src="figure/cktclaw2(1).png" alt="CktClaw logo" width="100%" />

# CktClaw

**The Autonomous Multi-Agent Ecosystem for Intelligent EDA**

[AlexWang](https://github.com/959AI994) · PhD Student · Shanghai Jiao Tong University · ACE Lab

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-372%20passing-brightgreen.svg)](tests/)

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
- **Multi-provider LLM** — Cloud DeepSeek / Anthropic Claude / OpenAI (and any OpenAI-compatible local endpoint such as vLLM / Ollama), plus local LogicRT & Qwen2.5-3B — switch **and configure API keys** at runtime with `/model`
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

Real-world runs — the `chip-rtl` orchestrator analysing an adder through `module_planning → rtl_coding → lint_check → cdc_rdc_analysis → synth_check → rtl_signoff`, driving Yosys / ABC / AI4EDA along the way:

<img src="figure/chip_design_skills.png" alt="Chip design orchestrator walkthrough (1/3)" width="100%" />

<img src="figure/chip_design_skills_2.png" alt="Chip design orchestrator walkthrough (2/3)" width="100%" />

<img src="figure/chip_design_skills_3.png" alt="Chip design orchestrator walkthrough (3/3)" width="100%" />

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
| `/chip-design-skills` | Manually browse 15 chip design domains (+ pipeline meta) |
| `/chip-pipeline [task]` | Cross-domain pipeline — verification↔RTL fix_request loop |
| `/model` | Pick a provider (DeepSeek / Claude / OpenAI / Local), configure its API key, and choose a model |
| `/session info` | View current session |
| `/clear` | New session |
| `/help` | Full help |

---

## 🔬 RTL-CLAW Skills (5 Pipeline Skills)

RTL optimization pipeline developed by Tongji EDA Lab + CUHK, embedded directly in CktClaw:

| Skill | Aliases | Description |
|-------|---------|-------------|
| `rtl-spec-analyzer` | `rtl-analyze`, `spec-analyze` | Analyze RTL + spec, extract Signal-to-Pin mappings |
| `testbench-generator` | `tb-gen`, `testbench-gen` | Generate SystemVerilog testbench from analysis output |
| `verilog-partition` | `rtl-partition`, `verilog-split` | Split RTL into sub-modules by always blocks |
| `verilog-optimization` | `rtl-opt`, `verilog-opt` | Yosys-based optimization of partitioned sub-modules |
| `verilog-merge` | `rtl-merge`, `verilog-join` | Merge optimized sub-modules back with equivalence check |

Skills work in prompt mode without OpenClaw infra, or full execution mode when `RTL_CLAW_ROOT` is set.

---

## 🔗 15 Chip Design Domains (+ Meta Pipeline)

CktClaw covers the full chip design flow. Each domain has its own multi-stage orchestrator, plus a **meta pipeline** for cross-domain feedback:

| Domain | Example Keywords | Stages |
|--------|-----------------|--------|
| **Pipeline (meta)** | fix_requests, cross-domain loop | 6 stages |
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

Each stage is LLM-driven. On failure, the orchestrator auto-loops back per configurable rules and escalates when the retry limit is reached. **P0 orchestration upgrades** (wired in Python, not template-only):

| Mechanism | What it does |
|-----------|----------------|
| **`design_state.json`** | Shared blackboard — constraints, fix_requests, QoR snapshots, history (`orchestrator/design_state.py`) |
| **Checkpoint resume** | After each stage, progress saved to `.cktclaw/runs/<run_id>/checkpoint.json`; resume on next run |
| **LLM `loop_back_to`** | Stage JSON `recommendation: loop_back_to:<stage>` triggers dynamic rollback (not only FAIL) |
| **Auto QoR extract** | Yosys / ABC / OpenSTA stdout parsed into stage QoR (`orchestrator/qor_extractor.py`) |
| **`/chip-pipeline`** | Meta orchestrator for verification↔RTL fix_request closed loop |

---

## 🏗️ Agent Architecture

CktClaw is a **multi-layered autonomous agent system** with cross-domain closed-loop capabilities. The following diagram shows the complete architecture from user input to tool execution:

```
┌─────────────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACE LAYER                                     │
│                                                                                       │
│   ┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────────┐      │
│   │  REPL    │    │ /commands    │    │ Natural Lang  │    │ /loop (v3)       │      │
│   │ main.py  │    │ /abc /yosys  │    │ "synthesize   │    │ cross-domain     │      │
│   │          │    │ /rltf /pareto│    │  this adder"  │    │ closed loop      │      │
│   └────┬─────┘    └──────┬───────┘    └──────┬────────┘    └────────┬─────────┘      │
│        └─────────────────┼───────────────────┼──────────────────────┘                 │
│                          ▼                   ▼                                         │
└──────────────────────────────────────────────────────────────────────────────────────┘
                           │                   │
┌──────────────────────────▼───────────────────▼──────────────────────────────────────┐
│                              ROUTING & DISPATCH LAYER                                 │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │  IntentRouter (handlers/intent_router.py)                                    │    │
│   │  • Keyword-based routing (40+ regex patterns, bilingual CN/EN)               │    │
│   │  • 14 chip-design domain routing                                             │    │
│   │  • Stateless — no cross-turn state leak                                      │    │
│   │  • Bare-keyword guard — single generic terms fall through to normal chat     │    │
│   └──────────────────────────────┬──────────────────────────────────────────────┘    │
│                                  │                                                    │
│   ┌──────────────────────────────▼──────────────────────────────────────────────┐    │
│   │  Harness (harness/)                                                          │    │
│   │  ┌─────────────┐ ┌────────────┐ ┌──────────────┐ ┌───────────┐ ┌────────┐  │    │
│   │  │ Bootstrap   │ │  Tasks     │ │   Skills     │ │Coordinator│ │ Query  │  │    │
│   │  │ (状态管理)  │ │ (生命周期) │ │ (技能注册)   │ │ (调度隔离)│ │ (循环) │  │    │
│   │  │ StateManager│ │ TaskManager│ │ SkillRegistry│ │ Coord.Mgr │ │QueryLoop│  │    │
│   │  └─────────────┘ └────────────┘ └──────────────┘ └───────────┘ └────────┘  │    │
│   └──────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
┌─────────────────────┐  ┌─────────────────────┐  ┌────────────────────────────────┐
│ ORCHESTRATION LAYER │  │  WORKFLOW LAYER      │  │ v3 SYSTEM LOOP LAYER           │
│                     │  │                      │  │ (loop/)                        │
│ ┌─────────────────┐│  │ ┌──────────────────┐ │  │                                │
│ │OrchestratorEngine││  │ │ RLTFCoordinator  │ │  │ ┌────────────────────────────┐ │
│ │                  ││  │ │ • RL loop driver │ │  │ │    GoalDecomposer          │ │
│ │ • Multi-stage    ││  │ │ • ABC sequences  │ │  │ │    (LLM → TaskGraph)       │ │
│ │   flow control   ││  │ │ • PPA reward     │ │  │ └─────────────┬──────────────┘ │
│ │ • LLM + tools    ││  │ └──────────────────┘ │  │               ▼                │
│ │ • JSON status    ││  │                      │  │ ┌────────────────────────────┐ │
│ │   extraction     ││  │ ┌──────────────────┐ │  │ │  CrossLayerTaskGraph (DAG) │ │
│ │ • WARN/followup  ││  │ │  Negotiation     │ │  │ │  • Dependencies            │ │
│ │   retry path     ││  │ │  Coordinator     │ │  │ │  • Verification criteria   │ │
│ │ • Escalation     ││  │ │ • Area Agent     │ │  │ │  • Critical path           │ │
│ │                  ││  │ │ • Delay Agent    │ │  │ └─────────────┬──────────────┘ │
│ │ ┌──────────────┐││  │ │ • Power Agent    │ │  │               ▼                │
│ │ │StateMachine  │││  │ │ • Nash Arbiter   │ │  │ ┌────────────────────────────┐ │
│ │ │ • proceed    │││  │ │ • Pareto Front   │ │  │ │     Domain Teams           │ │
│ │ │ • loop_back  │││  │ └──────────────────┘ │  │ │  ┌────┐ ┌────┐ ┌───────┐  │ │
│ │ │ • suspend    │││  │                      │  │ │  │EDA │ │Chip│ │AIInfra│  │ │
│ │ │ • escalate   │││  └──────────────────────┘  │ │  │Team│ │Team│ │Team   │  │ │
│ │ └──────────────┘││                            │ │  └──┬─┘ └──┬─┘ └───┬───┘  │ │
│ └─────────────────┘│                            │ └─────┼──────┼───────┼──────┘ │
│                     │                            │       ▼      ▼       ▼        │
│ 14 Domain Orchs:    │                            │ ┌────────────────────────────┐ │
│ • chip-synthesis    │                            │ │   VerificationRunner       │ │
│ • chip-rtl          │                            │ │   • Yosys/ABC/OpenSTA      │ │
│ • chip-verification │                            │ │   • Verilator/iVerilog     │ │
│ • chip-sta          │                            │ │   • pytest / compile check │ │
│ • chip-pd           │                            │ │   • Graceful no-tool path  │ │
│ • chip-formal       │                            │ └─────────────┬──────────────┘ │
│ • chip-dft          │                            │               ▼                │
│ • chip-hls          │                            │ ┌────────────────────────────┐ │
│ • chip-soc          │                            │ │    EvolutionEngine         │ │
│ • chip-architecture │                            │ │  • ExperienceStore         │ │
│ • chip-compiler     │                            │ │  • BottleneckAnalyzer      │ │
│ • chip-firmware     │                            │ │  • FeedbackGenerator       │ │
│ • chip-fpga         │                            │ │  • ConvergenceChecker      │ │
│ • chip-infrastructure                            │ │    (continue/converged/    │ │
│                     │                            │ │     stuck/pivot)           │ │
└─────────────────────┘                            │ └──────────────┬─────────────┘ │
                                                   │                │ feedback       │
                                                   │                └───── ↺ ───────┘ │
                                                   └────────────────────────────────┘
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                              AGENT EXECUTION LAYER                                    │
│                                                                                       │
│   ┌─────────────────────────────────────────────────────────────────────────────┐    │
│   │  AgentRuntime (agents/runtime.py)                                            │    │
│   │  • Max 5 concurrent agents                                                   │    │
│   │  • Event broadcasting                                                        │    │
│   │  • Timeout / budget enforcement                                              │    │
│   │  • Result collection                                                         │    │
│   └─────────────────────────────────┬───────────────────────────────────────────┘    │
│                                     │                                                 │
│   ┌─────────────────────────────────▼───────────────────────────────────────────┐    │
│   │  WorkerAgent (agents/worker.py)                                              │    │
│   │  • LLM query loop (call → tool_calls → execute → feed back)                 │    │
│   │  • Budget: max_turns=20, max_tokens=100K, timeout=300s                       │    │
│   │  • Tool sandbox via allowed_tools whitelist                                  │    │
│   │  • Status: CREATED → RUNNING → COMPLETED/FAILED/BUDGET_EXCEEDED             │    │
│   └─────────────────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────────────┐
│                              LLM PROVIDER LAYER                                       │
│                                                                                       │
│   ┌───────────────────────────────────────────────────────────────────────────────┐  │
│   │  ModelRouter (llm/router.py)  +  Credentials (api_credentials.py)              │  │
│   │  ┌─────────────┐ ┌──────────┐ ┌────────────────┐ ┌──────────────────────────┐ │  │
│   │  │ DeepSeek    │ │  Claude  │ │ OpenAI / compat│ │ Local (vLLM/Ollama/Qwen) │ │  │
│   │  │ (Cloud API) │ │(Anthropic│ │  (Cloud API)   │ │ LogicRT (on-device)      │ │  │
│   │  └─────────────┘ │  SDK)    │ └────────────────┘ └──────────────────────────┘ │  │
│   │                  └──────────┘                                                   │  │
│   │  • Runtime /model switch + in-CLI key setup → ~/.cktclaw/config.yaml           │  │
│   │  • Key resolution: env → yaml → interactive   • OAuth-token / missing-SDK guard│  │
│   │  • Streaming · Function calling · Failover chain · Retry w/ jitter · Compaction│  │
│   └───────────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────────────┐
│                              TOOL & SECURITY LAYER                                    │
│                                                                                       │
│  ┌───────────────────────────────────────────────────────────────────────────────┐   │
│  │  ToolRegistry (tools/registry.py)                                              │   │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────────┐ ┌────────┐  │   │
│  │  │ Yosys   │ │   ABC    │ │ OpenSTA  │ │ OpenROAD │ │Verilator│ │  Bash  │  │   │
│  │  │(synth)  │ │(logic opt│ │(timing)  │ │(PnR)     │ │(sim)    │ │(system)│  │   │
│  │  └─────────┘ └──────────┘ └──────────┘ └──────────┘ └─────────┘ └────────┘  │   │
│  │  ┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────────────────┐  │   │
│  │  │  File   │ │ Delegate │ │ NextPNR  │ │ MCP Servers (auto-configured)    │  │   │
│  │  │ (R/W)   │ │ (spawn)  │ │ (FPGA)   │ │ + SymbiYosys + Bambu + ...      │  │   │
│  │  └─────────┘ └──────────┘ └──────────┘ └──────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│  ┌───────────────────────────────────────────────────────────────────────────────┐   │
│  │  EDA Tool Detection (eda_tools/tool_detection.py)                              │   │
│  │  ┌──────────────────────────────────────────────────────────────────────────┐  │   │
│  │  │  detect_all_tools() — scans via shutil.which at startup                   │  │   │
│  │  │  • 20 open-source tools (Yosys, ABC, Verilator, OpenROAD, …)             │  │   │
│  │  │  • 7 proprietary tools (VCS, Xcelium, DC, Innovus, …)                    │  │   │
│  │  │  • ABC_PATH / OPENSTA_PATH env var overrides                              │  │   │
│  │  │  • ToolManifest.json written at startup, consumed by orchestrator         │  │   │
│  │  │  • Graceful MISSING status — never raises on cold-start                   │  │   │
│  │  └──────────────────────────────────────────────────────────────────────────┘  │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
│                                                                                       │
│  ┌───────────────────────────────────────────────────────────────────────────────┐   │
│  │  Security (security/)                                                          │   │
│  │  ┌─────────────────────┐  ┌──────────────────────────────────────────────┐    │   │
│  │  │  PathSandbox        │  │  ThreatPatterns                               │    │   │
│  │  │  • Allowed roots    │  │  • Command injection detection                │    │   │
│  │  │  • Denied globs     │  │  • EDA-specific dangerous patterns            │    │   │
│  │  │  • Symlink resolve  │  │  • Fork bomb / disk wipe prevention           │    │   │
│  │  └─────────────────────┘  └──────────────────────────────────────────────┘    │   │
│  │  ┌─────────────────────┐  ┌──────────────────────────────────────────────┐    │   │
│  │  │  ToolGuardrails     │  │  ToolRepair (tools/repair.py)                 │    │   │
│  │  │  • Pre/post checks  │  │  • Truncated / trailing-comma JSON repair     │    │   │
│  │  │  • Budget limits    │  │  • Fuzzy tool-name correction (Levenshtein)   │    │   │
│  │  │  • Loop prevention  │  │  • Schema-based type coercion                 │    │   │
│  │  └─────────────────────┘  └──────────────────────────────────────────────┘    │   │
│  └───────────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────────────┘
                                       │
┌──────────────────────────────────────▼──────────────────────────────────────────────┐
│                              MEMORY & OBSERVABILITY LAYER                             │
│                                                                                       │
│  ┌────────────────────────────────────────┐  ┌──────────────────────────────────┐   │
│  │  CktMem (cktmem/)                      │  │ TrajectoryLogger (trajectory.py) │   │
│  │  ┌──────────────────────────────────┐  │  │ • JSONL per session              │   │
│  │  │ 4-Layer Memory Stack             │  │  │ • user_message / assistant_msg   │   │
│  │  │ ┌────────────────────────────┐   │  │  │ • tool_call / tool_result        │   │
│  │  │ │ L1: Sliding Window (recent)│   │  │  │ • loop events (v3)              │   │
│  │  │ ├────────────────────────────┤   │  │  │ • failover / error              │   │
│  │  │ │ L2: LLM Compactor (summary)│   │  │  └──────────────────────────────────┘   │
│  │  │ ├────────────────────────────┤   │  │                                          │
│  │  │ │ L3: Semantic Search (embed)│   │  │  ┌──────────────────────────────────┐   │
│  │  │ ├────────────────────────────┤   │  │  │ ConfigLoader (config_loader.py)  │   │
│  │  │ │ L4: File-backed persistent │   │  │  │ • YAML-driven configuration      │   │
│  │  │ └────────────────────────────┘   │  │  │ • Tool paths, model prefs        │   │
│  │  └──────────────────────────────────┘  │  │ • Security policies              │   │
│  │  • VectorStore (embedding index)       │  └──────────────────────────────────┘   │
│  │  • TokenCounter (budget tracking)      │                                          │
│  │  • Compactor (auto-compress at 72.6%)  │                                          │
│  └────────────────────────────────────────┘                                          │
└──────────────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Summary

```
User Input
    │
    ├──[slash cmd]──→ Handler (abc/yosys/rltf/...) ──→ EDA Tool ──→ Result
    │
    ├──[NL task]───→ IntentRouter ──→ Domain Orchestrator ──→ Multi-stage LLM+Tools
    │                   (CN/EN)       (JSON repair + WARN path)
    │
    └──[/loop]────→ GoalDecomposer ──→ TaskGraph ──→ DomainTeams ──→ Verify ──→ Evolve
                                                         ▲                         │
                                                         └─────── feedback ────────┘
```

### Module Dependency Map

| Module | Depends On | Provides |
|--------|-----------|----------|
| `main.py` | harness, handlers, llm, skills | CLI entry point, REPL, RunContext wrapping |
| `harness/` | — | Bootstrap, Tasks, Skills, Query, Coordinator |
| `orchestrator/` | harness, llm, mcp, capability_registry | Multi-stage flow engine, Pydantic plan schema, JSON repair |
| `agents/` | llm, tools | WorkerAgent, AgentRuntime |
| `llm/` | api_credentials | ModelRouter, Providers, Streaming, Failover |
| `api_credentials.py` | config_loader | Secure key resolution (env → yaml → interactive) |
| `capability_registry.py` | tools, harness/skills, runtime | Unified Tool+Skill facade (audit/permissions/resilience) |
| `tools/` | security | ToolRegistry, EDA/Agent/System tools, ToolRepair |
| `security/` | — | PathSandbox, ThreatPatterns, Guardrails |
| `runtime/` | config_loader | RunContext, audit, permissions, data egress policy, budget, resilience |
| `eda_tools/` | — | ToolManifest, detect_all_tools, cold-start detection |
| `cktmem/` | — | ContextManager, SemanticSearch, VectorStore |
| `workflows/rltf/` | tools, llm | RLTFCoordinator, Executor, Reward |
| `workflows/pareto_negotiation/` | tools, llm | NegotiationCoordinator, NashArbiter |
| `loop/` (v3) | agents, tools, cktmem, llm | SystemLoopController, TaskGraph, Teams, EvolutionEngine |
| `skills/` | harness, workflows, loop | Skill registration + executors |
| `handlers/` | harness, skills, llm | IntentRouter, request dispatch, `/model`, `/doctor` |

### Runtime Governance & Reliability (`runtime/`)

Every invocation runs inside a **RunContext** (`.cktclaw/runs/<run_id>/`) that provides enterprise-grade controls for single-workstation deployments:

| Component | File | Role |
|-----------|------|------|
| **RunContext** | `runtime/run_context.py` | Per-run id + directory, run-scoped exception logs |
| **Audit trail** | `runtime/audit.py` | Append-only `events.jsonl`, secret redaction, arg hashing |
| **Permissions** | `runtime/permissions.py` + `policy.default.yaml` | Capability/provider allow-deny via `default` / `restricted` / `ci` profiles |
| **Data egress** | `runtime/data_policy.py` | IP/design classification, redaction, offline-mode enforcement |
| **Budget** | `runtime/budget.py` | Per-run & per-day token/cost quotas |
| **Resilience** | `runtime/resilience.py` | `with_timeout` · `CircuitBreaker` · `retry` (exp. backoff) |
| **Health** | `handlers/doctor_handler.py` | `cktclaw --doctor` / `/doctor` environment report (also in CI) |

### Test Suite

| Suite | Tests | Covers |
|-------|-------|--------|
| `tests/test_system_loop.py` | 52 unit tests | v3 loop: TaskGraph, GoalDecomposer, VerificationRunner, EvolutionEngine, SystemLoopController |
| `tests/test_*` (existing regression) | 174 tests | Intent router, tool repair, security, MCP, skills, EDA workflows |
| `tests/test_stress_intent_routing.py` | 27 stress tests | Intent hijacking, bilingual routing, adversarial inputs, stateless routing |
| `tests/test_stress_json_chaos.py` | 35 chaos tests | Truncated JSON, markdown contamination, trailing commas, WARN path, no infinite loops |
| `tests/test_stress_cold_start.py` | 31 cold-start tests | Missing tools, empty PATH, ABC_PATH env, VerificationRunner graceful no-tool path |
| `tests/test_task0..15_*.py` | enterprise hardening | Credentials, CapabilityRegistry, plan schema, MCP handshake, RunContext, audit, permissions, data egress, budget, resilience, doctor |
| **Total** | **372 tests** | **Full coverage: happy-path + adversarial + cold-start + governance + orchestrator P0** |

---

## 🤖 Choosing & Configuring Models (`/model`)

CktClaw resolves API keys in this order: **environment variable → `~/.cktclaw/config.yaml` → interactive setup via `/model`**. You never have to hardcode a key, and keys saved through `/model` persist across shells (no need to `source .env` each time).

### Quickest start — set a key via environment

```bash
export DEEPSEEK_API_KEY="sk-..."     # DeepSeek (default provider)
export ANTHROPIC_API_KEY="sk-ant-api..."   # Anthropic Claude (also: pip install anthropic)
export OPENAI_API_KEY="sk-..."       # OpenAI / OpenAI-compatible
```

### Configure interactively inside CktClaw

```bash
CktClaw > /model
# ↑↓ to navigate, Enter to confirm, Esc to cancel

╭───────────────────── 🔧 选择模型提供方 Provider ─────────────────────╮
│  ❯  🐋  DeepSeek          ✅ 已就绪 ◀ 当前                            │
│         云端 · 性价比高，中文友好                                     │
│      🦋  Anthropic Claude  ⛔ 未配置                                  │
│      🟢  OpenAI            ⛔ 未配置                                  │
│      💻  本地 / 自定义      ⛔ 未配置                                  │
╰──────────────────────────────────────────────────────────────────────╯
```

- **Pick a ready provider** → switches instantly.
- **Pick an unconfigured one** → CktClaw prompts for the API key (hidden input). For **Local / Custom** it asks for a Base URL + model (vLLM / Ollama / LM Studio). Values are saved to `~/.cktclaw/config.yaml` (chmod 600) and applied immediately — no restart.
- **Then choose a model** from the provider's list, or type a custom model name.

> 💡 A `sk-ant-oat...` value is a **Claude Code subscription OAuth token** and cannot call the API directly — CktClaw detects it and asks for a standard `sk-ant-api...` key instead.

`~/.cktclaw/config.yaml` example:

```yaml
llm:
  default_provider: deepseek
  deepseek:
    api_key: sk-...
    model: deepseek-chat
  claude:
    api_key: sk-ant-api...
    model: claude-sonnet-4-6
```

### Health check

```bash
cktclaw --doctor   # reports key/provider status, EDA tools, policy, offline mode
```

### Local Qwen Model (Privacy-First, No API Key)

CktClaw also supports [Qwen2.5-3B-Instruct](https://huggingface.co/Qwen/Qwen2.5-3B-Instruct) as a lightweight on-device engine — no internet or API key required after download.

```bash
conda activate cktclaw
python download_qwen.py   # ~6 GB, auto-uses ModelScope mirror
```

Once selected via `/model`, Qwen (or any local endpoint) drives all EDA tool calls (Yosys, AI4EDA, etc.) entirely on-device:

<img src="figure/local-qwen-yosys&ai4eda.png" alt="Local Qwen driving Yosys and AI4EDA tool calls" width="100%" />

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
