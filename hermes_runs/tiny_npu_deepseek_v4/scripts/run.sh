#!/bin/bash
#============================================================================
# run.sh — Full tiny_npu design flow
#   Step 1: Compile and simulate with Icarus Verilog
#   Step 2: Synthesize with Yosys
#   Step 3: Print summary
#============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJ_DIR="$(dirname "$SCRIPT_DIR")"
RTL_DIR="$PROJ_DIR/rtl"
OUT_DIR="$PROJ_DIR/outputs"
SCRIPTS_DIR="$PROJ_DIR/scripts"
mkdir -p "$OUT_DIR"

echo ""
echo "============================================================"
echo " Tiny NPU — Full Design Flow"
echo "============================================================"
echo "  Project : $PROJ_DIR"
echo "  RTL     : $RTL_DIR"
echo "  Outputs : $OUT_DIR"
echo "============================================================"
echo ""

#----------------------------------------------------------------------
# Step 1: Icarus Verilog compile & simulate
#----------------------------------------------------------------------
echo "[STEP 1/2] Icarus Verilog: compile & simulate"
echo "------------------------------------------------------------"

cd "$RTL_DIR"
iverilog -g2012 \
    -o "$OUT_DIR/tiny_npu_sim" \
    tiny_npu.v \
    tb_tiny_npu.v 2>&1 | tee "$OUT_DIR/compile.log"
echo "  Compile: OK  ($OUT_DIR/tiny_npu_sim)"

vvp "$OUT_DIR/tiny_npu_sim" 2>&1 | tee "$OUT_DIR/sim.log"
SIM_EXIT=$?
echo ""
echo "  Simulation exit code: $SIM_EXIT"
echo ""

#----------------------------------------------------------------------
# Step 2: Yosys synthesis
#----------------------------------------------------------------------
echo "[STEP 2/2] Yosys synthesis"
echo "------------------------------------------------------------"

cd "$SCRIPTS_DIR"
yosys -s yosys_synth.ys 2>&1 | tee "$OUT_DIR/yosys.log"
SYNTH_EXIT=$?

echo ""
echo "  Synthesis exit code: $SYNTH_EXIT"
echo ""

#----------------------------------------------------------------------
# Summary
#----------------------------------------------------------------------
echo "============================================================"
echo " Tiny NPU — Flow Complete"
echo "============================================================"
if [ -f "$OUT_DIR/tiny_npu_qor.rpt" ]; then
    echo "  QoR Report:"
    grep -E "(Number of|Cellular area|Total cells|DFF|AND|OR|XOR|MUX|ADD)" "$OUT_DIR/tiny_npu_qor.rpt" || true
fi
echo ""
echo "  Artifacts:"
echo "    $OUT_DIR/tiny_npu_sim     (simulation binary)"
echo "    $OUT_DIR/tiny_npu_synth.v  (synthesized netlist)"
echo "    $OUT_DIR/tiny_npu_synth.json (synthesis JSON)"
echo "    $OUT_DIR/tiny_npu_qor.rpt  (QoR report)"
echo "============================================================"
