# CktClaw 优化使用指南

本文档说明如何使用 CktClaw 的新增配置功能。

---

## 环境变量配置

### 1. 本地模型配置

支持使用 Qwen3.5-2B 或其他 HuggingFace 模型：

```bash
# 使用 HuggingFace Hub ID（首次使用会自动下载）
export CKTCLAW_LOCAL_MODEL=Qwen/Qwen3.5-2B

# 或使用本地路径
export CKTCLAW_LOCAL_MODEL=/path/to/your/local/model

# 启动 CktClaw
python main.py
```

**优先级**：
1. `CKTCLAW_CODEV_PATH` 环境变量（最高优先级）
2. `CKTCLAW_LOCAL_MODEL` 环境变量
3. GenEDA CodeV 目录（如果存在）
4. 仓库内 CodeV 目录（默认）

### 2. AI4EDA Toolkit 路径配置

如果 AI4EDA Toolkit 不在默认路径，可以自定义：

```bash
# 设置 AI4EDA Toolkit 路径
export CKTCLAW_AI4EDA_PATH=/your/custom/path/ai4eda-toolkit

# 启动 CktClaw
python main.py
```

**默认路径**：`/root/AI4EDA-OpenABC-Data-Toolkit/ai4eda-toolkit`

---

## 新功能说明

### 1. 工具调用去重

**功能**：自动检测并阻止 LLM 重复调用相同的工具和参数。

**工作原理**：
- 系统会记录每次工具调用的签名（工具名 + 参数哈希）
- 如果检测到重复调用，会跳过执行并提示 LLM
- 跨轮次持久化，避免在整个对话中重复调用

**示例**：
```
用户：请你用 yosys 帮我分析这个 aig 的各个指标
系统：[调用 yosys 一次，获取结果]
LLM：[尝试再次调用 yosys]
系统：⚠️ 检测到重复工具调用。您已经调用过相同的工具和参数。请直接总结之前的工具输出结果。
```

### 2. 清爽的终端输出

**改进**：删除了 debug 输出信息（`🔍 LLM Response Type` 等）

**效果**：
- 终端输出更简洁
- 只显示用户关心的内容
- 提升专业感

### 3. Workflow 需求确认

**功能**：在执行 chip-architecture 等工作流前，先询问用户需求。

**使用示例**：
```bash
CktClaw > /chip-architecture 分析电路

[Orchestrator Started]
architecture-orchestrator
Stages: spec_analysis → arch_exploration → perf_modelling → ...
Task: 分析电路

请描述您的具体需求（直接回车使用默认任务描述）:
需求 ❯ 我需要分析这个电路的面积和延时，目标是优化到 1ns 以内

✓ 已添加用户需求

将执行以下阶段：spec_analysis → arch_exploration → perf_modelling → ...
确认执行？[Y/n] ❯ Y

[开始执行工作流...]
```

**取消执行**：
- 输入 `n` 可以取消执行
- 按 `Ctrl+C` 也可以取消

---

## 下载 Qwen3.5-2B 模型

### 方法 1：自动下载（推荐）

```bash
# 设置环境变量
export CKTCLAW_LOCAL_MODEL=Qwen/Qwen3.5-2B

# 启动 CktClaw（首次启动会自动从 HuggingFace 下载）
python main.py

# 切换到 logicrt 引擎
CktClaw > /model
# 选择 logicrt
```

模型会自动下载到 HuggingFace 缓存目录（通常是 `~/.cache/huggingface/hub/`）。

### 方法 2：手动下载

```bash
# 使用 huggingface-cli 下载
pip install huggingface-hub
huggingface-cli download Qwen/Qwen3.5-2B --local-dir /path/to/save

# 设置环境变量指向本地路径
export CKTCLAW_LOCAL_MODEL=/path/to/save/Qwen3.5-2B

# 启动 CktClaw
python main.py
```

### 方法 3：使用 Git LFS

```bash
# 安装 Git LFS
git lfs install

# 克隆模型仓库
git clone https://huggingface.co/Qwen/Qwen3.5-2B /path/to/save

# 设置环境变量
export CKTCLAW_LOCAL_MODEL=/path/to/save

# 启动 CktClaw
python main.py
```

---

## 验证配置

运行验证脚本检查所有配置是否正确：

```bash
cd /root/cktclaw
./test_improvements.sh
```

预期输出：
```
==========================================
CktClaw 优化验证测试
==========================================

✓ Test 1: 配置加载测试
✓ Test 2: 环境变量覆盖测试
✓ Test 3: AI4EDA 路径覆盖测试
✓ Test 4: Python 语法检查
✓ Test 5: Debug 输出删除检查
✓ Test 6: 工具去重逻辑检查
✓ Test 7: Workflow 需求确认检查
✓ Test 8: 进度文档检查

==========================================
所有测试完成！
==========================================
```

---

## 常见问题

### Q1: 如何确认使用的是哪个模型？

启动 CktClaw 时会显示模型加载信息：

```
==================================================================
  Loading Local CodeV for Chat/Analysis (Lazy Loading)
  Path: Qwen/Qwen3.5-2B
  Target: Logical GPU 0 → Physical GPU 0
==================================================================
```

### Q2: 模型下载很慢怎么办？

可以使用国内镜像：

```bash
export HF_ENDPOINT=https://hf-mirror.com
export CKTCLAW_LOCAL_MODEL=Qwen/Qwen3.5-2B
python main.py
```

### Q3: 如何切换回 DeepSeek？

```bash
CktClaw > /model
# 选择 deepseek
```

### Q4: AI4EDA 路径配置不生效？

检查环境变量是否正确设置：

```bash
echo $CKTCLAW_AI4EDA_PATH
```

如果为空，说明环境变量未设置。请在启动 CktClaw 前设置：

```bash
export CKTCLAW_AI4EDA_PATH=/your/path/ai4eda-toolkit
python main.py
```

### Q5: 工具去重是否会影响正常使用？

不会。工具去重只针对**完全相同**的工具名和参数。如果参数不同，仍然会正常执行。

---

## 技术细节

### 工具去重算法

- 使用 MD5 哈希对工具参数进行指纹计算（取前8位）
- 签名格式：`(tool_name, args_hash)`
- 存储在会话状态中，跨轮次持久化

### 配置文件位置

所有配置都在 `/root/cktclaw/config.py` 中定义。

### 修改的文件清单

1. `/root/cktclaw/handlers/chat_handler_v2.py` — 删除 debug print
2. `/root/cktclaw/harness/query/query_loop_enhanced.py` — 工具去重逻辑
3. `/root/cktclaw/config.py` — AI4EDA 路径 + 本地模型配置
4. `/root/cktclaw/handlers/ai4eda_handler.py` — 使用配置化路径
5. `/root/cktclaw/orchestrator/engine.py` — 需求确认交互
6. `/root/cktclaw/todo/improve.md` — 进度记录

---

## 反馈与支持

如有问题或建议，请联系开发者：
- 开发者：王晶鑫（Jingxin Wang）
- 单位：上海交通大学 ACE 实验室

---

**CktClaw 现已具备工业水准的稳定性和可配置性！**
