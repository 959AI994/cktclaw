"""Tests for the generic Chip AutoDesign flow."""

import asyncio

from cktclaw.handlers.intent_router import detect_chip_design_intent
from cktclaw.skills.chip_autodesign_skill import register_chip_autodesign_skill
from cktclaw.workflows.chip_autodesign import ChipAutoDesignController
from cktclaw.workflows.chip_autodesign.controller import infer_design_kind
from cktclaw.workflows.tiny_npu.flow import _parse_yosys_qor


def test_autodesign_intent_routes_to_generic_flow():
    skill = detect_chip_design_intent(
        "请从规格和plan开始，自动完成RTL、仿真、综合、QoR和修复迭代"
    )
    assert skill == "chip-autodesign"


def test_single_point_rtl_still_routes_to_chip_rtl():
    skill = detect_chip_design_intent("write an RTL module for a simple arbiter")
    assert skill == "chip-rtl"


def test_design_kind_inference():
    assert infer_design_kind("design a sync fifo") == "sync_fifo"
    assert infer_design_kind("design an AXI-lite register block") == "axi_lite_reg_block"
    assert infer_design_kind("design a signed DSP MAC block") == "signed_dsp_mac"
    assert infer_design_kind("design a 16x16 Tiny NPU Tile") == "tiny_npu_tile"
    assert infer_design_kind("design a tiny_npu digit 6 recognizer") == "tiny_npu_tile"
    assert infer_design_kind("design crc8_stream_accel CRC-8 accelerator") == "custom"


def test_register_chip_autodesign_skill():
    from cktclaw.harness import get_skill_registry

    async def _run():
        await register_chip_autodesign_skill()
        registry = get_skill_registry()
        return await registry.get_skill("autodesign")

    skill = asyncio.run(_run())
    assert skill.name == "chip-autodesign"
    assert skill.user_invocable


def test_parse_yosys_new_and_old_qor():
    new_log = """
=== tiny_npu_tile_16x16 ===
    52906 wires
   468538 wire bits
   186676 cells
    90227   $_AND_
"""
    old_log = """
Number of wires:              12
Number of wire bits:          34
Number of cells:              5
  $and                         2
"""
    assert _parse_yosys_qor(new_log)["num_cells"] == 186676
    assert _parse_yosys_qor(old_log)["num_cells"] == 5


def test_autodesign_fifo_integration(tmp_path):
    async def _run():
        controller = ChipAutoDesignController(
            "design a sync fifo",
            project_dir=tmp_path / "fifo",
            force=True,
        )
        return await controller.run()

    result = asyncio.run(_run())
    assert result.status == "PASS"
    assert result.spec.design_kind == "sync_fifo"
    assert (tmp_path / "fifo" / "reports" / "autodesign_report.md").is_file()


def test_autodesign_axi_lite_integration(tmp_path):
    async def _run():
        controller = ChipAutoDesignController(
            "design an AXI-lite register block",
            project_dir=tmp_path / "axi",
            force=True,
        )
        return await controller.run()

    result = asyncio.run(_run())
    assert result.status == "PASS"
    assert result.spec.design_kind == "axi_lite_reg_block"


def test_autodesign_dsp_mac_integration(tmp_path):
    async def _run():
        controller = ChipAutoDesignController(
            "design a signed DSP MAC block",
            project_dir=tmp_path / "dsp",
            force=True,
        )
        return await controller.run()

    result = asyncio.run(_run())
    assert result.status == "PASS"
    assert result.spec.design_kind == "signed_dsp_mac"


def test_autodesign_tiny_npu_integration(tmp_path):
    async def _run():
        controller = ChipAutoDesignController(
            "design a 16x16 Tiny NPU Tile for handwritten digit inference",
            project_dir=tmp_path / "tiny",
            force=True,
        )
        return await controller.run()

    result = asyncio.run(_run())
    assert result.status == "PASS"
    assert result.spec.design_kind == "tiny_npu_tile"
    assert result.spec.inference_target["target_digit"] == 6
    assert result.stages["simulate"]["coverage"]["digit_6_recognition"] == "PASS"
    assert result.qor["num_cells"] > 0
