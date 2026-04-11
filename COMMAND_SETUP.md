# CktClaw 终端命令使用说明

## ✅ 命令已配置完成

现在你可以在任何目录直接使用 `cktclaw` 命令启动 Python 版本的 CktClaw 项目。

## 🚀 使用方法

### 启动 CktClaw
```bash
cktclaw
```

### 常用命令

启动后，你可以使用以下命令：

#### 基本命令
- `/help` - 显示帮助信息
- `/exit` - 退出 CktClaw
- `/clear` - 清除当前会话，开始新会话

#### 会话管理
- `/session info` - 查看当前会话信息
- `/sessions list` - 列出所有会话
- `/session switch <id>` - 切换到指定会话

#### EDA 工具
- `/reverse <aig_file>` - AIG 逆向分析（完整流程）
- `abc <command>` - 执行 ABC 命令
- `yosys <command>` - 执行 Yosys 命令

#### 引擎切换
- `/engine` - 切换 LLM 引擎（LogicRT/DeepSeek）
- `/model` - 选择模型

#### 对话
- 直接输入文本 - 与 AI 对话（使用 QueryLoop + Skills 路由）

## 📊 系统特性

### 已激活的功能
- ✅ **Harness 架构**：5 个核心模块（Bootstrap, Tasks, Skills, Coordinator, Query）
- ✅ **CktMem 记忆系统**：4 层上下文 + 81.4% 自动压缩
- ✅ **QueryLoop 中枢循环**：Tool-Result 配对 + 自动错误自愈
- ✅ **Skills 路由**：3 个技能（abc, yosys, reverse）

### 对话增强
当你与 AI 对话时，系统会：
1. 自动检测工具调用需求
2. 路由到对应的 Skill 执行器
3. 验证 Tool-Result 配对
4. 自动修复缺失的 tool_result
5. 返回最终响应

## 🔧 配置信息

### 命令位置
- **符号链接**: `/home/wjx/.nvm/versions/node/v22.18.0/bin/cktclaw`
- **实际脚本**: `/home/wjx/pythonproject/cktclaw/bin/cktclaw`
- **项目目录**: `/home/wjx/pythonproject/cktclaw`

### 备份信息
- **旧版本备份**: `/home/wjx/.nvm/versions/node/v22.18.0/bin/cktclaw.bak`
- 如需恢复旧版本：
  ```bash
  mv /home/wjx/.nvm/versions/node/v22.18.0/bin/cktclaw.bak \
     /home/wjx/.nvm/versions/node/v22.18.0/bin/cktclaw
  ```

## 📝 示例使用

### 示例 1：AIG 逆向分析
```bash
$ cktclaw
CktClaw> /reverse /path/to/circuit.aig
# 系统会自动执行 AIG → PT → Verilog → Validate → Analyze 流程
```

### 示例 2：与 AI 对话
```bash
CktClaw> 请帮我分析这个电路的功能
# AI 会基于历史上下文回答，并自动调用相关工具
```

### 示例 3：执行 ABC 命令
```bash
CktClaw> abc read test.aig; strash; balance; print_stats
# 系统会通过 abc_skill 执行命令
```

### 示例 4：查看会话信息
```bash
CktClaw> /session info
# 显示当前会话的消息数、Token 数、压缩次数等
```

## 🎯 技术架构

```
终端命令: cktclaw
    ↓
Python 启动脚本
    ↓
CktClaw Main (main.py)
    ↓
┌─────────────────────────────────┐
│ Chat Handler V2 (QueryLoop)     │
│ - Tool-Result 配对              │
│ - 自动错误自愈                  │
│ - Skills 路由                   │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ Skills (abc, yosys, reverse)    │
└─────────────────────────────────┘
    ↓
┌─────────────────────────────────┐
│ EDA Tools (ABCRunner, etc.)     │
└─────────────────────────────────┘
```

## ✅ 验证

运行以下命令验证配置：
```bash
which cktclaw
# 应该输出: /home/wjx/.nvm/versions/node/v22.18.0/bin/cktclaw

ls -la $(which cktclaw)
# 应该显示符号链接指向 /home/wjx/pythonproject/cktclaw/bin/cktclaw

cktclaw --help
# 应该显示 CktClaw 欢迎界面
```

---

**配置完成时间**: 2024-04-11 22:50
**配置人员**: Claude (Sonnet 4.5)
**状态**: ✅ 可用
