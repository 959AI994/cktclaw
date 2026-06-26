# CktClaw 全栈 E2E 重跑摘要（Round 2）

Date: 2026-06-25  
Commit: `dcd99b1` — Refine full-chip skill routing

## 本次改动验证

| 改动 | 验证结果 |
|------|----------|
| `intent_router.py` 新增 `erie-verilog-generator` 规则（优先于 testbench-generator） | Prompt 1 正确 auto-route → **PASS** |
| `eda_agent_runner.py` 输出 `SPECIALIST_DISPATCH` 标记 | Prompt 8 未触发 stage 级 FAIL→dispatch（见下） |

## 验收矩阵

| ID | 结论 | 备注 |
|----|------|------|
| 0 | PASS | preflight 25/25 |
| 10 | PASS | verilator + sby |
| 1 | **PASS** | 命中 `erie-verilog-generator`，引用 `deps/verilog-generator` |
| 2–6 | PASS | DeepSeek live (~7.5 min) |
| 7 | PASS | eda-only ~697s |
| 8 | **PARTIAL** | chip-rtl `rtl_coding` failed；fix_requests=24；**无** `SPECIALIST_DISPATCH` / `rtl_repair_agent` 输出 |
| 9 | PASS | 七 Agent ~34 min |

## Prompt 8 说明

`broken_fifo.v` 在 chip-rtl 阶段 `rtl_coding` 即 failed（1/6 阶段通过），但 `/chip-system` 汇总输出里未出现 `SPECIALIST_DISPATCH`。可能原因：

- EDA 链在 chip-rtl orchestrator 内部失败后未抛到 `EDAAgentRunner` 的 exception 路径
- 或 chip-verification 未跑到真实 FAIL，未触发 `FAILURE_SPECIALISTS`

建议下一步：在 Prompt 8 日志中搜索 `live_eda_run_r2.log` 的 `chip-verification` / `chip-synthesis` 阶段，或让 `chip-rtl` fail 时向上传递 fix_request。

## 日志

- `tests/e2e_reports/live_skills_run_r2.log`
- `tests/e2e_reports/live_eda_run_r2.log`
- `tests/e2e_reports/09_full_chip_system_r2.log`
