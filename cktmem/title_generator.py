"""
会话标题生成器

根据用户的第一条消息或会话内容自动生成有意义的标题
"""

import re
from typing import Optional


async def generate_session_title_with_llm(
    user_message: str,
    assistant_response: Optional[str] = None,
    llm_analyzer=None,
    max_length: int = 40,
) -> str:
    """
    使用 LLM 生成会话标题

    Args:
        user_message: 用户的第一条消息
        assistant_response: 助手回复（可选）
        llm_analyzer: LLM 分析器实例
        max_length: 最大标题长度

    Returns:
        生成的会话标题
    """
    if llm_analyzer is None:
        # Fallback to rule-based generation
        return generate_session_title(user_message, max_length)

    try:
        # 构造 prompt
        prompt = f"""请为这个 EDA 电路设计对话生成一个简短精准的标题（不超过{max_length}个字符）。

用户问题：
{user_message[:500]}

{"助手回复：" if assistant_response else ""}
{assistant_response[:500] if assistant_response else ""}

标题生成要求：
1. 提取核心关键词：电路名、模块名、文件名、操作类型
2. 如果提到具体实体（如"上海交通大学"），使用常见缩写（如"SJTU"）
3. 优先格式：<操作> <对象>（如"分析 SJTU 电路"、"优化 RISC-V CPU"、"逆向 adder.aig"）
4. 如果是代码片段，提取模块名（如"counter 模块"）
5. 保持简洁专业，不要啰嗦

直接输出标题，不要任何解释或前缀："""

        # 调用 LLM
        messages = [{"role": "user", "content": prompt}]

        # 使用 DeepSeek 生成标题（快速且便宜）
        response = llm_analyzer.chat_with_deepseek(messages)

        if isinstance(response, str):
            title = response.strip()
        elif isinstance(response, dict):
            title = response.get("content", "").strip()
        else:
            title = str(response).strip()

        # 清理标题
        title = title.replace('"', '').replace("'", '').strip()

        # 移除可能的前缀和后缀
        prefixes = ["标题：", "标题:", "Title:", "Title：", "**", "##"]
        for prefix in prefixes:
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
            if title.endswith(prefix):
                title = title[:-len(prefix)].strip()

        # 移除 markdown 格式
        title = title.replace('**', '').replace('*', '').strip()

        # 截断到最大长度
        if len(title) > max_length:
            title = title[:max_length-3] + "..."

        # 验证标题有效性
        if len(title) < 2 or len(title) > max_length + 10:
            # Fallback to rule-based
            return generate_session_title(user_message, max_length)

        return title

    except Exception as e:
        # Fallback to rule-based generation
        return generate_session_title(user_message, max_length)


def generate_session_title(user_message: str, max_length: int = 40) -> str:
    """
    根据用户消息生成会话标题

    策略：
    1. 提取关键词（电路名、文件名、操作）
    2. 清理特殊字符
    3. 截断到合适长度
    4. 添加默认前缀（如果太短）

    Args:
        user_message: 用户的第一条消息
        max_length: 最大标题长度

    Returns:
        生成的会话标题
    """
    # 清理消息
    message = user_message.strip()

    # 提取文件路径中的文件名
    file_pattern = r'([a-zA-Z0-9_-]+\.(v|aig|blif|verilog|sv))'
    file_match = re.search(file_pattern, message, re.IGNORECASE)
    if file_match:
        filename = file_match.group(1)
        return f"分析 {filename}"

    # 提取电路模块名
    module_pattern = r'module\s+([a-zA-Z0-9_]+)'
    module_match = re.search(module_pattern, message, re.IGNORECASE)
    if module_match:
        module_name = module_match.group(1)
        return f"电路 {module_name}"

    # 检测常见操作关键词
    keywords = {
        "逆向": "逆向工程",
        "reverse": "逆向工程",
        "综合": "逻辑综合",
        "synthesis": "逻辑综合",
        "优化": "电路优化",
        "optimize": "电路优化",
        "分析": "电路分析",
        "analyze": "电路分析",
        "验证": "电路验证",
        "verify": "电路验证",
        "时序": "时序分析",
        "timing": "时序分析",
        "面积": "面积优化",
        "area": "面积优化",
        "功耗": "功耗分析",
        "power": "功耗分析",
    }

    for keyword, title_prefix in keywords.items():
        if keyword in message.lower():
            # 尝试提取后续的名词
            pattern = rf'{keyword}\s+([a-zA-Z0-9_\u4e00-\u9fa5]+)'
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                target = match.group(1)
                return f"{title_prefix} {target}"[:max_length]
            return title_prefix

    # 如果消息很短，直接使用
    if len(message) <= max_length:
        # 清理特殊字符
        clean_message = re.sub(r'[^\w\s\u4e00-\u9fa5-]', '', message)
        if clean_message.strip():
            return clean_message.strip()[:max_length]

    # 提取前几个词
    words = re.findall(r'[\w\u4e00-\u9fa5]+', message)
    if words:
        title = ' '.join(words[:5])
        if len(title) > max_length:
            title = title[:max_length-3] + "..."
        return title

    # 默认标题
    return "新会话"


def generate_title_from_context(
    user_message: str,
    assistant_response: Optional[str] = None,
    circuit_name: Optional[str] = None,
) -> str:
    """
    根据上下文生成更智能的标题

    Args:
        user_message: 用户消息
        assistant_response: 助手回复（可选）
        circuit_name: 电路名称（可选）

    Returns:
        生成的标题
    """
    # 优先使用电路名称
    if circuit_name:
        return f"电路 {circuit_name}"

    # 使用基础生成器
    title = generate_session_title(user_message)

    # 如果有助手回复，尝试提取更多信息
    if assistant_response and title == "新会话":
        # 从助手回复中提取模块名
        module_pattern = r'模块\s*[：:]\s*([a-zA-Z0-9_]+)'
        match = re.search(module_pattern, assistant_response)
        if match:
            return f"电路 {match.group(1)}"

        # 提取功能描述
        function_pattern = r'(这是|实现了?)\s*([^\n。，,]{5,30})'
        match = re.search(function_pattern, assistant_response)
        if match:
            description = match.group(2).strip()
            return f"{description}"[:40]

    return title


# 测试用例
if __name__ == "__main__":
    test_cases = [
        "/reverse adder.aig",
        "分析这个加法器电路",
        "module counter(input clk, output [7:0] count);",
        "帮我优化这个电路的面积",
        "这个电路的时序怎么样？",
        "请进行逻辑综合",
        "verify the design",
        "analyze timing for cpu_core.v",
        "这是一个很长的消息，包含了很多内容，需要被截断处理，确保标题不会太长",
        "hi",
    ]

    print("会话标题生成测试：\n")
    for i, msg in enumerate(test_cases, 1):
        title = generate_session_title(msg)
        print(f"{i}. 消息: {msg[:50]}")
        print(f"   标题: {title}\n")
