"""
RLTF Sequence Generator - LLM 序列生成器

使用 LLM 生成 ABC 优化序列，基于历史反馈进行强化学习。
"""

import os
import re
from typing import List, Dict, Any, Optional
from openai import OpenAI

from .types import SequenceGenerationContext, PPAMetrics


class RLTFSequenceGenerator:
    """
    RLTF 序列生成器

    使用 LLM 生成 ABC 优化序列，支持：
    - 基于历史反馈的上下文学习
    - 多样性探索
    - 序列验证
    """

    # ABC 可用命令列表
    VALID_ABC_COMMANDS = [
        "strash",      # 结构化哈希
        "balance",     # 平衡 AIG
        "rewrite",     # 代数重写
        "refactor",    # 重构
        "resub",       # 重新替换
        "compress",    # 迭代压缩
        "compress2",   # 高级压缩
        "retime",      # 重定时
        "dch",         # 选择哈希
        "if",          # FPGA 映射
        "map",         # 标准单元映射
    ]

    def __init__(
        self,
        model: str = "deepseek-chat",
        temperature: float = 0.7,
        max_tokens: int = 512,
    ):
        """
        初始化序列生成器

        Args:
            model: LLM 模型名称
            temperature: 采样温度
            max_tokens: 最大 token 数
        """
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

        # 初始化 OpenAI 客户端（兼容 DeepSeek API）
        api_key = os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
        )

    async def generate(self, context: SequenceGenerationContext) -> str:
        """
        生成 ABC 优化序列

        Args:
            context: 生成上下文

        Returns:
            ABC 命令序列（分号分隔）
        """
        # 构建 LLM Prompt
        prompt = self._build_prompt(context)

        # 调用 LLM
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": self._get_system_prompt(),
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

            # 提取生成的序列
            generated_text = response.choices[0].message.content.strip()
            sequence = self._extract_sequence(generated_text)

            # 验证序列
            if not self._validate_sequence(sequence):
                # 如果验证失败，返回默认序列
                return self._get_default_sequence(context.current_iteration)

            return sequence

        except Exception as e:
            # 如果 LLM 调用失败，返回默认序列
            print(f"LLM generation failed: {e}, using default sequence")
            return self._get_default_sequence(context.current_iteration)

    def _get_system_prompt(self) -> str:
        """
        获取系统提示

        Returns:
            系统提示文本
        """
        return """You are an expert in logic synthesis optimization using ABC (A System for Sequential Synthesis and Verification).

Your task is to generate ABC command sequences to optimize AIG (And-Inverter Graph) circuits for better PPA (Power, Performance, Area) metrics.

Available ABC commands:
- strash: Structural hashing (creates AIG structure)
- balance: Balance the AIG to reduce depth
- rewrite: Algebraic rewriting for area reduction
- refactor: Refactoring for area/delay trade-off
- resub: Resubstitution for area reduction
- compress: Iterative compression (combines rewrite + refactor)
- compress2: Advanced compression with more iterations
- retime: Retiming for delay optimization
- dch: Don't-care-based hashing
- if: FPGA technology mapping
- map: Standard cell technology mapping

Guidelines:
1. Start with 'strash' to create proper AIG structure
2. Use 'balance' to reduce logic depth
3. Combine multiple optimization passes for better results
4. Typical sequence length: 3-8 commands
5. Consider the trade-off between area and delay

Output format: Just the semicolon-separated command sequence, e.g.:
strash; balance; rewrite; refactor"""

    def _build_prompt(self, context: SequenceGenerationContext) -> str:
        """
        构建 LLM Prompt

        Args:
            context: 生成上下文

        Returns:
            Prompt 文本
        """
        lines = [
            f"Generate an ABC command sequence for iteration {context.current_iteration}.",
            "",
            "Context:",
        ]

        # 添加最佳序列信息
        if context.best_sequence and context.best_reward is not None:
            lines.append(f"- Best sequence so far: {context.best_sequence}")
            lines.append(f"- Best reward: {context.best_reward:.4f}")

            if context.current_metrics:
                lines.append(f"- Current best metrics:")
                lines.append(f"  - Area: {context.current_metrics.area}")
                lines.append(f"  - Delay: {context.current_metrics.delay:.4f} ns")

        # 添加目标信息
        if context.target_metrics:
            lines.append("")
            lines.append("Target metrics:")
            for key, value in context.target_metrics.items():
                lines.append(f"  - {key}: {value}")

        # 添加最近尝试的序列
        if context.previous_sequences:
            lines.append("")
            lines.append("Recent attempts (last 5):")
            recent_count = min(5, len(context.previous_sequences))
            for i in range(recent_count):
                idx = len(context.previous_sequences) - recent_count + i
                seq = context.previous_sequences[idx]
                reward = context.previous_rewards[idx]
                lines.append(f"  {i+1}. {seq} (reward: {reward:.4f})")

        lines.append("")
        lines.append("Generate a NEW ABC command sequence that:")
        lines.append("1. Explores different optimization strategies")
        lines.append("2. Aims to improve both area and delay")
        lines.append("3. Avoids repeating recent unsuccessful attempts")
        lines.append("")
        lines.append("Output only the command sequence (semicolon-separated):")

        return "\n".join(lines)

    def _extract_sequence(self, text: str) -> str:
        """
        从 LLM 输出中提取 ABC 序列

        Args:
            text: LLM 生成的文本

        Returns:
            提取的 ABC 序列
        """
        # 移除 markdown 代码块
        text = re.sub(r'```[a-z]*\n?', '', text)
        text = re.sub(r'```', '', text)

        # 查找包含 ABC 命令的行
        lines = text.split('\n')
        for line in lines:
            line = line.strip()

            # 跳过空行和注释
            if not line or line.startswith('#') or line.startswith('//'):
                continue

            # 检查是否是有效序列
            if self._looks_like_sequence(line):
                return line

        # 如果没有找到，返回第一个非空行
        for line in lines:
            line = line.strip()
            if line:
                return line

        return "strash; balance; rewrite"

    def _looks_like_sequence(self, text: str) -> bool:
        """
        检查文本是否看起来像 ABC 序列

        Args:
            text: 文本

        Returns:
            是否像 ABC 序列
        """
        # 检查是否包含分号
        if ';' not in text:
            return False

        # 检查是否包含至少一个有效命令
        commands = [cmd.strip() for cmd in text.split(';')]
        for cmd in commands:
            if cmd in self.VALID_ABC_COMMANDS:
                return True

        return False

    def _validate_sequence(self, sequence: str) -> bool:
        """
        验证 ABC 序列的有效性

        Args:
            sequence: ABC 序列

        Returns:
            是否有效
        """
        if not sequence or not sequence.strip():
            return False

        # 分割命令
        commands = [cmd.strip() for cmd in sequence.split(';')]

        # 检查命令数量
        if len(commands) < 1 or len(commands) > 15:
            return False

        # 检查每个命令是否有效
        for cmd in commands:
            if not cmd:
                continue

            # 提取命令名（忽略参数）
            cmd_name = cmd.split()[0] if ' ' in cmd else cmd

            if cmd_name not in self.VALID_ABC_COMMANDS:
                return False

        return True

    def _get_default_sequence(self, iteration: int) -> str:
        """
        获取默认序列（当 LLM 失败时使用）

        Args:
            iteration: 当前迭代次数

        Returns:
            默认 ABC 序列
        """
        # 预定义的优化序列池
        default_sequences = [
            "strash; balance; rewrite",
            "strash; rewrite; refactor",
            "strash; balance; rewrite; refactor",
            "strash; rewrite; rewrite; refactor",
            "strash; balance; rewrite; rewrite; balance",
            "strash; compress",
            "strash; compress2",
            "strash; balance; compress",
            "strash; rewrite; resub",
            "strash; balance; rewrite; resub; balance",
        ]

        # 根据迭代次数循环选择
        idx = iteration % len(default_sequences)
        return default_sequences[idx]

    def generate_diverse_sequences(
        self,
        context: SequenceGenerationContext,
        count: int = 5,
    ) -> List[str]:
        """
        生成多个多样化的序列

        Args:
            context: 生成上下文
            count: 生成数量

        Returns:
            序列列表
        """
        sequences = []

        # 临时提高温度以增加多样性
        original_temp = self.temperature
        self.temperature = min(1.0, self.temperature + 0.2)

        try:
            for _ in range(count):
                # 使用同步方式调用（简化实现）
                import asyncio
                sequence = asyncio.run(self.generate(context))
                sequences.append(sequence)

        finally:
            # 恢复原始温度
            self.temperature = original_temp

        return sequences
