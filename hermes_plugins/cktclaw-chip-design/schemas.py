"""Tool schemas exposed by the CktClaw chip-design Hermes plugin."""

from __future__ import annotations

from .tool_runtime import TOOL_SPECS


def _eda_schema(tool_name: str, spec: dict) -> dict:
    return {
        "name": f"cktclaw_chip_run_{tool_name}",
        "description": spec["description"],
        "parameters": {
            "type": "object",
            "properties": {
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Raw CLI arguments passed to the tool. Prefer this over command when possible.",
                    "default": [],
                },
                "command": {
                    "type": "string",
                    "description": "Optional raw command line. Parsed with shlex and only used when args/script fields are absent.",
                },
                "script": {
                    "type": "string",
                    "description": "Inline Yosys or SPICE script when supported by the selected tool.",
                },
                "script_file": {
                    "type": "string",
                    "description": "Path to an existing tool script file.",
                },
                "tcl_script": {
                    "type": "string",
                    "description": "Inline Tcl for OpenSTA/OpenROAD/Magic/KLayout-style tools.",
                },
                "netlist_file": {
                    "type": "string",
                    "description": "SPICE or circuit netlist file for analog simulation tools.",
                },
                "working_dir": {
                    "type": "string",
                    "description": "Working directory for the process. Defaults to the active Hermes workspace.",
                },
                "timeout_s": {
                    "type": "integer",
                    "description": "Execution timeout in seconds.",
                    "minimum": 1,
                    "maximum": 7200,
                },
                "env": {
                    "type": "object",
                    "description": "Optional environment overrides. Use sparingly for paths and PDK variables.",
                    "additionalProperties": {"type": "string"},
                },
            },
        },
    }


CKTCLAW_CHIP_INSTALL_TOOLCHAIN = {
    "name": "cktclaw_chip_install_toolchain",
    "description": "Clone chip-design skill/tool repositories and optionally install open-source EDA tools under CKTCLAW_CHIP_ROOT.",
    "parameters": {
        "type": "object",
        "properties": {
            "root": {
                "type": "string",
                "description": "Install root. Defaults to ${CKTCLAW_CHIP_ROOT:-~/.cktclaw-chip}.",
            },
            "mode": {
                "type": "string",
                "enum": ["minimal", "full"],
                "description": "minimal clones repos only. full also attempts open-source EDA tool setup.",
                "default": "minimal",
            },
            "dry_run": {
                "type": "boolean",
                "description": "List exact actions without writing files.",
                "default": False,
            },
            "include_hermes": {
                "type": "boolean",
                "description": "Also clone NousResearch/hermes-agent under the install root for local validation.",
                "default": False,
            },
            "skip_opensta_build": {
                "type": "boolean",
                "description": "In full mode, locate OpenSTA but do not build it from source if absent.",
                "default": False,
            },
            "timeout_s": {
                "type": "integer",
                "description": "Overall installer timeout.",
                "minimum": 30,
                "maximum": 14400,
            },
        },
    },
}

CKTCLAW_CHIP_DOCTOR = {
    "name": "cktclaw_chip_doctor",
    "description": "Report chip-design dependency repositories, EDA binaries, and generated environment paths.",
    "parameters": {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Toolchain root to inspect."},
            "format": {
                "type": "string",
                "enum": ["json", "markdown"],
                "description": "Return format.",
                "default": "json",
            },
        },
    },
}

CKTCLAW_CHIP_GENERATE_MCP_CONFIG = {
    "name": "cktclaw_chip_generate_mcp_config",
    "description": "Generate Hermes mcp_servers config for selected chip EDA wrappers.",
    "parameters": {
        "type": "object",
        "properties": {
            "tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Tool names to expose. Defaults to all supported open-source EDA tools.",
            },
            "output_path": {
                "type": "string",
                "description": "Optional path to write the generated JSON snippet.",
            },
            "root": {"type": "string", "description": "Toolchain root for env defaults."},
        },
    },
}

CKTCLAW_CHIP_SPEC_TEMPLATE = {
    "name": "cktclaw_chip_spec_template",
    "description": "Create a chip/IP design spec template with interfaces, PPA targets, verification gates, and handoff artifacts.",
    "parameters": {
        "type": "object",
        "properties": {
            "domain": {
                "type": "string",
                "enum": ["digital", "analog", "ams", "rf", "fpga", "hls", "soc"],
                "description": "Design domain.",
                "default": "digital",
            },
            "block_name": {"type": "string", "description": "Top block or IP name."},
            "target": {"type": "string", "description": "Technology, FPGA part, or PDK target."},
            "format": {
                "type": "string",
                "enum": ["markdown", "json"],
                "description": "Template format.",
                "default": "markdown",
            },
        },
    },
}

CKTCLAW_CHIP_FLOW_PLAN = {
    "name": "cktclaw_chip_flow_plan",
    "description": "Map a chip-design request to recommended CktClaw plugin skills, open-source tools, gates, and artifacts.",
    "parameters": {
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "User request or design task."},
            "domain": {
                "type": "string",
                "enum": ["auto", "digital", "analog", "ams", "rf", "fpga", "hls", "soc"],
                "description": "Preferred domain. auto infers from task keywords.",
                "default": "auto",
            },
            "constraints": {"type": "string", "description": "PPA, process, board, or verification constraints."},
        },
        "required": ["task"],
    },
}

CKTCLAW_CHIP_CLOSURE_CHECK = {
    "name": "cktclaw_chip_closure_check",
    "description": "Inspect digital RTL run artifacts and classify compile, simulation, Yosys synthesis, netlist, and QoR closure status with debug hints.",
    "parameters": {
        "type": "object",
        "properties": {
            "project_dir": {
                "type": "string",
                "description": "Project directory containing rtl, scripts, and outputs subdirectories.",
            },
            "outputs_dir": {
                "type": "string",
                "description": "Optional explicit outputs directory. Defaults to <project_dir>/outputs.",
            },
            "expected_pass_regex": {
                "type": "string",
                "description": "Regex that proves simulation success. Defaults to TEST PASS|PASS.",
            },
            "qor_report": {
                "type": "string",
                "description": "Optional explicit QoR report path.",
            },
            "netlist": {
                "type": "string",
                "description": "Optional explicit synthesized netlist path.",
            },
        },
        "required": ["project_dir"],
    },
}

EDA_TOOL_SCHEMAS = [_eda_schema(name, spec) for name, spec in TOOL_SPECS.items()]

ALL_TOOL_SCHEMAS = [
    CKTCLAW_CHIP_INSTALL_TOOLCHAIN,
    CKTCLAW_CHIP_DOCTOR,
    CKTCLAW_CHIP_GENERATE_MCP_CONFIG,
    CKTCLAW_CHIP_SPEC_TEMPLATE,
    CKTCLAW_CHIP_FLOW_PLAN,
    CKTCLAW_CHIP_CLOSURE_CHECK,
    *EDA_TOOL_SCHEMAS,
]
