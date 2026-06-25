# Full-Chip E2E Fixtures

测试夹具目录，供 CktClaw 全栈 E2E（CLI + DeepSeek）使用。

## 文件说明

| 文件 | Prompt | 预期行为 |
|------|--------|----------|
| `workspace/bad_counter.v` | 2 (RTL Repair) | 位宽不匹配 + 异步/错误复位逻辑；修复后同步高电平复位清零，每拍 +1 |
| `workspace/broken_fifo.v` | 8 (故障派发) | FIFO 读指针 off-by-one 且未递减 count；verification 应 FAIL 并触发 specialist |
| `workspace/top.sv` | 10 (工具 smoke) | 简单 8-bit 加法器，含轻微 style 问题供 verible lint |
| `workspace/include/defs.svh` | 10 (slang) | `top.sv` 的 include 目录 |

## 部署到 workspace

在项目根目录执行：

```bash
mkdir -p runs/sat_accum workspace workspace/include
cp -r tests/fixtures/full_chip_e2e/workspace/* workspace/
# 或: ln -sf "$(pwd)/tests/fixtures/full_chip_e2e/workspace/"* workspace/
```

## 验证 gate 建议

- **bad_counter.v**: `verilator --lint-only workspace/bad_counter.v` 应报错
- **broken_fifo.v**: 综合/仿真 testbench 应 FAIL（由 chip-verification stage 捕获）
- **top.sv**: verilator lint 应 PASS；verible/slang 视安装情况 skipped 或 PASS

## 修复目标（Prompt 2）

```verilog
always @(posedge clk) begin
    if (rst)
        count <= 8'd0;
    else
        count <= count + 8'd1;
end
```

（将 `rst_n` 改为同步高有效 `rst` 或按 prompt 规格调整端口名。）
