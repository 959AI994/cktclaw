# Optimization Report (EvolutionEngine)

No critical bottlenecks detected from design_state QoR.

---

## Agent Analysis
# OptimizerAgent — Performance Optimization Report

## Project: /chip-system — Streaming Packet Checksum Accelerator
## Target: 1 byte/cycle throughput | Workdir: ./runs/checksum_accel

---

## 1. Current Performance Baseline

### 1.1 Timing Analysis
| Metric | Value | Status |
|--------|-------|--------|
| WNS (setup) | -0.35 ns | ❌ Violation |
| Yosys synthesis errors | 1 | ❌ Critical |
| Area concern | True | ⚠️ Warning |
| Optimization candidates | 14 identified | Need action |

### 1.2 Pipeline Stage Status
| Stage | Status | Issue |
|-------|--------|-------|
| chip-rtl | ❌ Failed (fr-1, fr-3) | Synthesis/elaboration error |
| chip-pd | ❌ Failed (fr-2) | Place & route failure |
| chip-sta | ⚠️ Completed | WNS violation detected |
| HLS signoff | ✅ Complete | But with warnings |
| RTL signoff | ⚠️ Complete | Timing violation + area concern |

### 1.3 Throughput Assessment
- **Target**: 1 byte/cycle (8 Gbps @ 1 GHz or equivalent)
- **Current estimate**: Degraded due to timing closure issues
- **Bottleneck**: Critical path in checksum datapath (likely CRC/IP checksum accumulation logic)

---

## 2. Bottleneck Analysis

### 2.1 Primary Bottlenecks (Priority Order)

| # | Bottleneck | Evidence | Impact |
|---|------------|----------|--------|
| 1 | **Synthesis error** | yosys_error=1, chip-rtl failed | Blocks all downstream stages |
| 2 | **Timing violation** | WNS=-0.35ns, chip-sta completed | Limits max frequency, throughput |
| 3 | **Area concern** | area_concern=True | May limit FPGA fit or increase power |
| 4 | **14 optimization candidates** | Identified but not addressed | Missed optimization opportunities |
| 5 | **Pipeline stage failures** | fr-1, fr-2, fr-3 open | Indicates systematic issues |

### 2.2 Root Cause Analysis

**Synthesis Error (yosys_error=1)**:
- Likely cause: Unsupported SystemVerilog construct, missing module instantiation, or combinatorial loop in checksum datapath
- Affected modules: Checksum core, packet parser, or accumulation logic

**Timing Violation (-0.35ns)**:
- Critical path: Likely in the checksum accumulation tree (adder chain for IP checksum or CRC computation)
- Contributing factors: Deep combinatorial logic without pipelining, high fan-out control signals

**Area Concern**:
- Probable cause: Over-engineered datapath width (e.g., 64-bit or 128-bit processing when 8-bit/cycle is target)
- Unoptimized state machines or redundant logic

---

## 3. Optimization Recommendations

### 3.1 Immediate Fixes (Priority: Critical)

#### R1: Fix Synthesis Error
**Action**: 
- Run `yosys -v3` to get detailed error message
- Check for: missing `always_comb` vs `always_ff`, incomplete case statements, width mismatches
- Verify all module instantiations match their declarations

**Expected Improvement**: Unblock chip-rtl stage, enable full synthesis flow

**Risk**: Low — standard debug procedure

#### R2: Pipeline Checksum Datapath
**Action**:
- Insert pipeline registers at 2-3 stages in the checksum accumulation logic
- For IP checksum (16-bit one's complement): 2-stage pipeline (add → complement)
- For CRC: 3-4 stages depending on polynomial complexity

**Expected Improvement**: WNS improvement of 0.3-0.5ns, enabling timing closure

**Risk**: Low — adds 2-3 cycle latency, throughput remains 1 byte/cycle

### 3.2 Short-term Optimizations (Priority: High)

#### R3: Reduce Datapath Width to 8-bit
**Action**:
- Change from wider datapath (if currently >8-bit) to 8-bit processing
- Implement byte-serial checksum accumulation
- Use shift register for packet data input

**Expected Improvement**: 
- Area reduction: 30-50%
- Timing improvement: 0.2-0.4ns
- Power reduction: 25-40%

**Risk**: Medium — requires RTL modification, verify with existing testbench

#### R4: Implement Retiming for Critical Path
**Action**:
- Use Yosys `retime -D` option to automatically retime registers
- Alternatively, manually move register boundaries in checksum core

**Expected Improvement**: WNS improvement of 0.1-0.2ns

**Risk**: Low — automated tool option, verify functional equivalence

#### R5: Optimize Control Logic
**Action**:
- Reduce fan-out of state machine control signals
- Use one-hot encoding for FSM (if not already)
- Implement clock gating for inactive datapath sections

**Expected Improvement**: 
- Timing: 0.05-0.1ns
- Dynamic power: 15-20%

**Risk**: Low — standard optimization techniques

### 3.3 Medium-term Optimizations (Priority: Medium)

#### R6: Implement Multi-cycle Paths
**Action**:
- Identify non-critical paths that can take >1 cycle
- Add timing exceptions for: reset paths, test modes, configuration registers

**Expected Improvement**: Relax timing constraints on non-critical paths

**Risk**: Low — requires careful path analysis

#### R7: Optimize Memory Interface
**Action**:
- If using BRAM for packet buffering, ensure registered outputs
- Implement double-buffering for continuous streaming

**Expected Improvement**: Throughput guarantee of 1 byte/cycle

**Risk**: Low — standard memory interface design

#### R8: Compiler Optimization Flags
**Action**:
- Add `-retime` and `-noalumacc` to Yosys synthesis script
- Use `-flatten` for better optimization
- Set `-abc9` for improved technology mapping

**Expected Improvement**: 5-10% timing improvement

**Risk**: Low — tool flags, verify with formal equivalence

### 3.4 Long-term Optimizations (Priority: Low)

#### R9: Micro-architecture Exploration
**Action**:
- Evaluate checksum algorithm variants (parallel vs serial)
- Consider hardware-software partitioning for complex checksums
- Implement speculative accumulation for multiple packets

**Expected Improvement**: Potential 2x throughput increase

**Risk**: High — significant RTL changes, requires re-verification

#### R10: Power Optimization
**Action**:
- Implement operand isolation for unused datapath sections
- Use clock gating at module level
- Optimize memory access patterns

**Expected Improvement**: 20-30% power reduction

**Risk**: Medium — requires careful validation

---

## 4. Implementation Plan

### Phase 1: Critical Fixes (Day 1-2)
| Day | Task | Owner | Expected Outcome |
|-----|------|-------|------------------|
| 1 | Fix synthesis error (R1) | RTL Designer | chip-rtl passes |
| 1-2 | Pipeline checksum datapath (R2) | RTL Designer | WNS improvement |

### Phase 2: Short-term Optimizations (Day 3-5)
| Day | Task | Owner | Expected Outcome |
|-----|------|-------|------------------|
| 3 | Reduce datapath width (R3) | RTL Designer | Area reduction |
| 3-4 | Implement retiming (R4) | EDA Engineer | Timing closure |
| 4-5 | Optimize control logic (R5) | RTL Designer | Power reduction |

### Phase 3: Medium-term (Day 6-10)
| Day | Task | Owner | Expected Outcome |
|-----|------|-------|------------------|
| 6-7 | Multi-cycle paths (R6) | STA Engineer | Relaxed constraints |
| 7-8 | Memory interface (R7) | RTL Designer | Throughput guarantee |
| 8-10 | Compiler flags (R8) | EDA Engineer | Synthesis quality |

### Phase 4: Long-term (Day 11-14)
| Day | Task | Owner | Expected Outcome |
|-----|------|-------|------------------|
| 11-12 | Micro-architecture (R9) | Architect | Throughput improvement |
| 13-14 | Power optimization (R10) | All | Power reduction |

---

## 5. Expected Improvements Summary

| Metric | Current | After R1-R5 | After R1-R8 | After R1-R10 |
|--------|---------|-------------|-------------|--------------|
| WNS | -0.35ns | -0.05ns | 0.00ns | +0.05ns |
| Area | Concern | Normal | Optimized | Optimized |
| Throughput | Degraded | 1 byte/cycle | 1 byte/cycle | 1-2 byte/cycle |
| Power | High | Moderate | Low | Very Low |
| Synthesis | Error | Clean | Clean | Clean |

---

## 6. Verification Strategy

### After Each Optimization
1. **Functional equivalence**: Run existing testbench
2. **Timing analysis**: STA with updated constraints
3. **Area report**: Compare before/after synthesis
4. **Power estimation**: Toggle rate analysis

### Final Verification
1. **Formal equivalence**: Compare RTL before/after optimization
2. **Full regression**: All test cases pass
3. **FPGA bring-up**: On-board validation at target frequency
4. **Driver integration**: Software driver works with optimized hardware

---

## 7. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| RTL changes break functionality | Medium | High | Incremental verification |
| Timing closure still fails | Low | High | Multiple optimization techniques |
| Area exceeds FPGA budget | Low | Medium | Monitor area after each step |
| Power exceeds budget | Low | Medium | Power analysis after R5 |

---

## 8. Recommendation

**Recommend iteration**: Yes

**Rationale**: 
- Current state has 3 open fix requests and critical timing violation
- 14 optimization candidates identified but not addressed
- Systematic issues in RTL design and synthesis flow

**Iteration scope**:
1. Fix synthesis error (R1) — unblock pipeline
2. Implement pipelining (R2) — address timing
3. Reduce datapath width (R3) — address area
4. Re-run full EDA flow
5. Verify throughput target achieved

**Expected iteration duration**: 5-7 days

---

## 9. Next Steps for Other Agents

| Agent | Action Required |
|-------|----------------|
| **ArchitectAgent** | Approve datapath width reduction (R3) |
| **EDAAgent** | Implement retiming (R4) and compiler flags (R8) |
| **CompilerAgent** | Update synthesis script with optimization flags |
| **RuntimeAgent** | Monitor power and throughput after optimization |
| **PMAgent** | Update schedule for 5-7 day iteration |

---

*Report generated by OptimizerAgent | EvolutionEngine pre-analysis integrated*