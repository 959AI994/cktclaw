# 🚀 CktClaw Harness Services 快速启动指南

## 📋 前置检查

在开始之前，确保所有功能已正确安装：

```bash
# 1. 进入项目目录
cd /home/wjx/pythonproject/cktclaw

# 2. 运行测试验证
python test_harness_complete.py      # 核心功能测试
python verify_integration.py         # 集成验证
python test_next_steps.py            # 下一步行动测试

# 期望输出：所有测试通过 ✅
```

---

## 🎯 核心功能使用

### 1. 自动压缩 (Auto Compact)

**自动触发**：当 Token 数超过 150,000 时自动触发

```bash
# 启动 CktClaw
python main.py

# 进行多轮对话
> 分析这个电路
> 继续分析电路的时序特性
> 详细说明关键路径
> ... (继续对话直到 Token > 150K)

# 观察自动压缩
[INFO] Token count: 155000 > threshold: 150000
[INFO] Triggering auto-compact...
[Compact] Trigger: auto
[Compact] Pre-compact tokens: 155000
[Compact] Post-compact tokens: 42000
[Compact] Tokens saved: 113000
💾 Compacted conversation, saved ~113,000 tokens
```

**手动触发**：

```python
# 在代码中手动触发
from cktmem.compactor import Compactor

result = await compactor.manual_compact(
    session_id=session_id,
    custom_instructions="Keep all technical details",
)
```

---

### 2. 工具编排 (Tool Orchestration)

**自动并行/串行执行**：

```bash
# 使用需要多个工具的命令
> 读取 circuit.v 文件，搜索所有 .v 文件，然后写入分析结果到 report.txt

# 观察工具编排
[DEBUG] Tool orchestration: 3 batches
[DEBUG] Batch 1: parallel, 2 tools (Read, Grep)
[DEBUG] Batch 2: serial, 1 tool (Write)
[DEBUG] Executing Read and Grep concurrently...
[DEBUG] Executing Write serially...
```

**在代码中使用**：

```python
from harness.services.tools import run_tools, MessageUpdate

tool_calls = [
    {"id": "1", "name": "Read", "input": {"file_path": "test.v"}},
    {"id": "2", "name": "Grep", "input": {"pattern": "module"}},
    {"id": "3", "name": "Write", "input": {"file_path": "out.txt"}},
]

async for update in run_tools(tool_calls, tool_executor, context):
    if update.message:
        print(f"Tool result: {update.message}")
    if update.new_context:
        context = update.new_context
```

---

### 3. 速率限制 (Rate Limiting)

**自动生效**：已集成到 `chat_handler_v2.py`

```bash
# 快速发送多个请求
> 分析电路
> 分析电路
> 分析电路

# 观察速率限制
[yellow]⏳ Rate limit reached. Waiting 5.2s...[/yellow]
[正在分析...]
```

**配置速率限制**：

编辑 `handlers/chat_handler_v2.py`：

```python
def get_rate_limiter() -> RateLimiter:
    config = RateLimitConfig(
        max_requests_per_minute=60,      # 每分钟最多 60 个请求
        max_tokens_per_minute=100_000,   # 每分钟最多 100K tokens
    )
    return RateLimiter(config)
```

---

### 4. Hook 系统

**使用内置 Hooks**：

```python
# Pre-Compact Hook 自动执行
# Post-Compact Hook 自动显示压缩统计
# Session Start Hook 自动生成欢迎消息
```

**注册自定义 Hook**：

```python
from harness.hooks.pre_compact import PreCompactHook, register_pre_compact_hook

class MyCustomHook(PreCompactHook):
    def __init__(self):
        super().__init__("my_custom_hook", priority=50)

    async def execute(self, hook_input, abort_signal=None):
        # 自定义逻辑
        print(f"Pre-compact hook triggered: {hook_input.trigger}")

        return PreCompactHookResult(
            new_custom_instructions="Keep all technical details and code examples",
            user_display_message="Custom pre-compact processing...",
        )

# 注册钩子
register_pre_compact_hook(MyCustomHook())
```

**Post-Compact Hook 示例**：

```python
from harness.hooks.post_compact import PostCompactHook, register_post_compact_hook

class StatisticsHook(PostCompactHook):
    def __init__(self):
        super().__init__("statistics_hook", priority=60)

    async def execute(self, hook_input, abort_signal=None):
        # 记录统计信息
        compression_ratio = (
            hook_input.tokens_saved / hook_input.pre_compact_token_count * 100
        )

        return PostCompactHookResult(
            user_display_message=f"Compression ratio: {compression_ratio:.1f}%",
        )

register_post_compact_hook(StatisticsHook())
```

---

### 5. 文件附件恢复

**自动恢复**：压缩后自动恢复最近访问的文件

```python
# 压缩前读取文件
> 读取 circuit.v
> 读取 testbench.v
> 读取 constraints.sdc

# 压缩发生
[INFO] Compacting conversation...
[INFO] Restoring 3 files from cache...

# 压缩后，模型仍然可以访问这些文件
```

**配置文件恢复**：

编辑 `harness/services/compact/attachments.py`：

```python
POST_COMPACT_MAX_FILES_TO_RESTORE = 5      # 最多恢复 5 个文件
POST_COMPACT_TOKEN_BUDGET = 50_000         # Token 预算 50K
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000   # 每个文件最多 5K tokens
```

**手动创建附件**：

```python
from harness.services.compact import create_and_format_file_attachments
import time

# 文件状态
read_file_state = {
    "circuit.v": {
        "content": "module top(...);",
        "timestamp": time.time(),
    },
}

# 创建附件
messages = await create_and_format_file_attachments(
    read_file_state=read_file_state,
)
```

---

## 🔧 配置选项

### 压缩配置

编辑 `cktmem/models.py`：

```python
@dataclass
class CompactConfig:
    auto_compact_threshold: int = 150_000  # 自动压缩阈值
    target_tokens: int = 40_000            # 目标 Token 数
    buffer_tokens: int = 13_000            # 缓冲 Token 数
```

### 速率限制配置

编辑 `handlers/chat_handler_v2.py`：

```python
config = RateLimitConfig(
    max_requests_per_minute=60,       # 请求限制
    max_tokens_per_minute=100_000,    # Token 限制
    max_concurrent_requests=10,       # 并发限制
)
```

### 文件附件配置

编辑 `harness/services/compact/attachments.py`：

```python
POST_COMPACT_MAX_FILES_TO_RESTORE = 5      # 文件数量
POST_COMPACT_TOKEN_BUDGET = 50_000         # Token 预算
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000   # 单文件限制
```

---

## 📊 监控和调试

### 查看压缩统计

```python
from cktmem.storage import Storage

storage = Storage("cktclaw_sessions.db")

# 查询压缩历史
compact_history = await storage.get_compact_history(session_id)

for record in compact_history:
    print(f"Type: {record['compact_type']}")
    print(f"Tokens saved: {record['tokens_saved']}")
    print(f"Time: {record['created_at']}")
```

### 查看速率限制统计

```python
from handlers.chat_handler_v2 import get_rate_limiter

limiter = get_rate_limiter()
stats = limiter.get_stats()

print(f"Requests: {stats['requests_count']}/{stats['max_requests_per_minute']}")
print(f"Tokens: {stats['tokens_count']}/{stats['max_tokens_per_minute']}")
print(f"Concurrent: {stats['concurrent_requests']}/{stats['max_concurrent_requests']}")
```

### 启用调试日志

```python
import logging

# 启用调试日志
logging.basicConfig(level=logging.DEBUG)

# 或者只启用特定模块
logging.getLogger('harness.services.compact').setLevel(logging.DEBUG)
logging.getLogger('harness.services.tools').setLevel(logging.DEBUG)
```

---

## 🐛 常见问题

### Q1: 压缩没有触发？

**检查**：
1. Token 数是否超过阈值（默认 150K）
2. `auto_compact` 是否设置为 `True`
3. 查看日志是否有错误

```python
# 手动检查 Token 数
from harness.services.compact import estimate_tokens

tokens = estimate_tokens(messages)
print(f"Current tokens: {tokens}")
```

### Q2: 速率限制太严格？

**解决**：调整配置

```python
# 增加限制
config = RateLimitConfig(
    max_requests_per_minute=120,      # 增加到 120
    max_tokens_per_minute=200_000,    # 增加到 200K
)
```

### Q3: 文件附件没有恢复？

**检查**：
1. 文件是否在排除列表中
2. 文件是否已在保留消息中
3. Token 预算是否足够

```python
# 查看排除的文件类型
from harness.services.compact.attachments import should_exclude_from_restore

is_excluded = should_exclude_from_restore("test.db")
print(f"Is excluded: {is_excluded}")
```

### Q4: Hook 没有执行？

**检查**：
1. Hook 是否已注册
2. Hook 优先级是否正确
3. Hook 是否抛出异常

```python
# 查看已注册的 hooks
from harness.hooks.pre_compact import _registered_hooks

for hook in _registered_hooks:
    print(f"Hook: {hook.name}, Priority: {hook.priority}")
```

---

## 📚 更多资源

### 文档

- [QUICK_REFERENCE.md](./QUICK_REFERENCE.md) - 快速参考
- [INTEGRATION_PROGRESS.md](./INTEGRATION_PROGRESS.md) — 集成进度与 Harness 文档合并归档（原 HARNESS_INTEGRATION_GUIDE / FINAL_SUMMARY 等已并入）

### 测试

```bash
# 运行所有测试
python test_harness_complete.py
python verify_integration.py
python test_next_steps.py
```

### 示例

查看测试文件中的示例：
- `test_harness_complete.py` - 功能示例
- `test_next_steps.py` - Hook 和附件示例

---

## ✅ 验证安装

运行以下命令验证所有功能正常：

```bash
# 1. 测试核心功能
python test_harness_complete.py

# 期望输出：
# ✅ 模块导入测试 - 通过
# ✅ 图片清理测试 - 通过
# ✅ 附件清理测试 - 通过
# ✅ 自动压缩策略测试 - 通过
# ✅ Context Modifier 测试 - 通过
# ✅ 完整压缩（带 LLM）测试 - 通过
# 总计: 6/6 通过 (100%)

# 2. 验证集成
python verify_integration.py

# 期望输出：
# ✅ 自动压缩集成 - 通过
# ✅ 工具编排集成 - 通过
# ✅ 微压缩集成 - 通过
# ✅ chat_handler_v2 集成 - 通过
# ✅ 完整调用链 - 通过
# ✅ 触发条件 - 通过
# 总计: 6/6 通过 (100%)

# 3. 测试下一步行动
python test_next_steps.py

# 期望输出：
# ✅ 速率限制集成 - 通过
# ✅ Hook 系统 - 通过
# ✅ 文件附件恢复 - 通过
# ✅ 完整集成 - 通过
# 总计: 4/4 通过 (100%)
```

如果所有测试都通过，说明安装成功！🎉

---

## 🚀 开始使用

```bash
# 启动 CktClaw
python main.py

# 开始对话
> 你好
> 分析这个电路
> ... (享受自动压缩、工具编排、速率限制等功能)
```

---

**祝使用愉快！** 🎊

如有问题，请查看文档或运行测试进行调试。
