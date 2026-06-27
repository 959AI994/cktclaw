# CktClaw Chip Design Plugin for Hermes Agent

This directory is a Hermes-native plugin that packages CktClaw's chip-design knowledge, specs, open-source EDA wrappers, toolchain install helpers, and MCP snippets without carrying CktClaw memory, chat, UI, or agent runtime code.

## Install Into Hermes

From the CktClaw repository root:

```bash
python3 hermes_plugins/cktclaw-chip-design/scripts/install_into_hermes.py --enable
```

Use `--mode copy` if symlinks are not desirable. Use `--clone-hermes` to clone `NousResearch/hermes-agent` under the Hermes profile before installing the plugin.

## Install Chip Toolchain Repos

```bash
python3 hermes_plugins/cktclaw-chip-design/scripts/install_toolchain.py --mode minimal --json
```

The default root is `${CKTCLAW_CHIP_ROOT:-~/.cktclaw-chip}`. Minimal mode shallow-clones the chip-design skill/tool repos. Full mode also attempts open-source EDA setup:

```bash
python3 hermes_plugins/cktclaw-chip-design/scripts/install_toolchain.py --mode full --json
```

## Main Hermes Tools

- `cktclaw_chip_install_toolchain`
- `cktclaw_chip_doctor`
- `cktclaw_chip_generate_mcp_config`
- `cktclaw_chip_spec_template`
- `cktclaw_chip_flow_plan`
- `cktclaw_chip_run_yosys`
- `cktclaw_chip_run_iverilog`
- `cktclaw_chip_run_vvp`
- `cktclaw_chip_run_verilator`
- `cktclaw_chip_run_sby`
- `cktclaw_chip_run_opensta`
- `cktclaw_chip_run_openroad`
- `cktclaw_chip_run_ngspice`
- `cktclaw_chip_run_magic`
- `cktclaw_chip_run_klayout`
- `cktclaw_chip_run_netgen`

The remaining tool wrappers cover Bambu, gem5, Xyce, OpenVAF, openEMS, OpenLane2, and AI4EDA when installed.

## Skills

The plugin bundles categorized read-only skills under `skills/`:

- `core`
- `digital`
- `analog`
- `rtl-enhancement`
- `fpga`

Hermes registers them with the plugin namespace, for example `skill_view("cktclaw-chip-design:digital-rtl-design")`.
