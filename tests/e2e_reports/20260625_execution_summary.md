# CktClaw 全栈 E2E 执行摘要（DeepSeek 已配置）

Date: 2026-06-25（重跑）

## 配置

- `cktclaw/.env` 中已启用 `DEEPSEEK_API_KEY`
- `cktclaw --doctor` → **api_keys: OK**
- Preflight: 25 pytest passed

## 验收矩阵（Live DeepSeek）

| ID | 结论 | 耗时/备注 |
|----|------|-----------|
| 0 | PASS | doctor + pytest |
| 10 | PASS | verilator + sby；verible/slang skipped |
| 1 | **PARTIAL** | 被 intent 路由到 `testbench-generator`，skill 未注册 → 未走 `erie-verilog-generator` |
| 2 | PASS | rtl-repair + 工具证据 (~191s) |
| 3 | PASS | formal / sby |
| 4 | PASS | hls-generator |
| 5 | PASS | analog-design 16 域 |
| 6 | PASS | PPA 三类优化 |
| 7 | PASS | chip-system eda-only (~419s) |
| 8 | PASS | fix_requests=21 open (~188s)；specialist 派发需人工查 log |
| 9 | PASS | 七 Agent 全流程 (~35 min) |

日志：
- `tests/e2e_reports/live_skills_run.log`
- `tests/e2e_reports/live_eda_run.log`
- `tests/e2e_reports/09_full_chip_system.log`

## Prompt 1 待改进

Prompt 1 因关键词命中 `testbench-generator` 被 auto-route，但 E2E runner 未注册 RTL-CLAW 子 skill。修复方向：

- 在 runner 中 `register_rtl_claw_skills()`，或
- 使用显式 `/erie-verilog-generator ...` prompt

## 安全提示

API Key 已写入本地 `.env`（已在 `.gitignore`）。若在聊天中明文分享过 key，建议在 DeepSeek 控制台轮换。
