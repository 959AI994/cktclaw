"""
Mock Sequence Generator - 用于测试的模拟序列生成器

不需要 API key，使用预定义的优化序列进行测试。
"""

from typing import List
from .types import SequenceGenerationContext


class MockSequenceGenerator:
    """
    模拟序列生成器

    用于测试环境，不需要真实的 LLM API。
    """

    # 预定义的优化序列池
    OPTIMIZATION_SEQUENCES = [
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
        "strash; balance; rewrite; refactor; balance",
        "strash; rewrite; refactor; rewrite",
        "strash; compress; balance",
        "strash; balance; compress2",
        "strash; rewrite; resub; rewrite",
    ]

    def __init__(self):
        """初始化模拟生成器"""
        self.call_count = 0

    async def generate(self, context: SequenceGenerationContext) -> str:
        """
        生成 ABC 优化序列

        Args:
            context: 生成上下文

        Returns:
            ABC 命令序列
        """
        # 根据迭代次数选择不同的序列
        idx = context.current_iteration % len(self.OPTIMIZATION_SEQUENCES)
        sequence = self.OPTIMIZATION_SEQUENCES[idx]

        self.call_count += 1

        # 如果有最佳序列，偶尔尝试在其基础上变化
        if context.best_sequence and context.current_iteration % 3 == 0:
            # 尝试在最佳序列基础上添加一个命令
            variations = [
                f"{context.best_sequence}; balance",
                f"{context.best_sequence}; rewrite",
                f"{context.best_sequence}; refactor",
            ]
            var_idx = context.current_iteration % len(variations)
            return variations[var_idx]

        return sequence

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
        for i in range(count):
            idx = (context.current_iteration + i) % len(self.OPTIMIZATION_SEQUENCES)
            sequences.append(self.OPTIMIZATION_SEQUENCES[idx])
        return sequences
