"""
Session title generation — LLM-assisted with a deterministic fallback.
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
    Ask the configured chat model for a short EDA-oriented title.

    Falls back to ``generate_session_title`` when no analyzer is provided or
    the model returns unusable text.
    """
    if llm_analyzer is None:
        return generate_session_title(user_message, max_length)

    try:
        prompt = f"""Generate a short, precise title (max {max_length} characters) for this EDA / circuit-design chat.

User message:
{user_message[:500]}

{f"Assistant reply:{chr(10)}{assistant_response[:500]}" if assistant_response else ""}

Rules:
1. Capture circuit names, module names, filenames, and the main action.
2. Prefer ``<verb> <object>`` (e.g., "Analyze SJTU netlist", "Optimize RISC-V CPU", "Reverse adder.aig").
3. If the user names an institution, prefer a well-known acronym when obvious.
4. For code snippets, prefer the module name.
5. Stay professional and avoid filler.

Output the title only — no quotes, prefixes, or explanations."""

        messages = [{"role": "user", "content": prompt}]

        response = llm_analyzer.chat_with_deepseek(messages)

        if isinstance(response, str):
            title = response.strip()
        elif isinstance(response, dict):
            title = response.get("content", "").strip()
        else:
            title = str(response).strip()

        title = title.replace('"', '').replace("'", '').strip()

        prefixes = ["Title:", "Title：", "**", "##"]
        for prefix in prefixes:
            if title.startswith(prefix):
                title = title[len(prefix):].strip()
            if title.endswith(prefix):
                title = title[:-len(prefix)].strip()

        title = title.replace('**', '').replace('*', '').strip()

        if len(title) > max_length:
            title = title[:max_length - 3] + "..."

        if len(title) < 2 or len(title) > max_length + 10:
            return generate_session_title(user_message, max_length)

        return title

    except Exception:
        return generate_session_title(user_message, max_length)


def generate_session_title(user_message: str, max_length: int = 40) -> str:
    """
    Lightweight keyword / regex heuristics when the LLM path is unavailable.
    """
    message = user_message.strip()

    file_pattern = r'([a-zA-Z0-9_-]+\.(v|aig|blif|verilog|sv))'
    file_match = re.search(file_pattern, message, re.IGNORECASE)
    if file_match:
        filename = file_match.group(1)
        return f"Analyze {filename}"[:max_length]

    module_pattern = r'module\s+([a-zA-Z0-9_]+)'
    module_match = re.search(module_pattern, message, re.IGNORECASE)
    if module_match:
        module_name = module_match.group(1)
        return f"Circuit {module_name}"[:max_length]

    keywords = {
        "reverse": "Reverse engineering",
        "synthesis": "Synthesis",
        "optimize": "Optimization",
        "analysis": "Analysis",
        "analyze": "Analysis",
        "verify": "Verification",
        "timing": "Timing",
        "area": "Area",
        "power": "Power",
    }

    lower = message.lower()
    for keyword, title_prefix in keywords.items():
        if keyword in lower:
            pattern = rf'{re.escape(keyword)}\s+([a-zA-Z0-9_]+)'
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                target = match.group(1)
                return f"{title_prefix} {target}"[:max_length]
            return title_prefix[:max_length]

    if len(message) <= max_length:
        clean_message = re.sub(r'[^\w\s-]', '', message)
        if clean_message.strip():
            return clean_message.strip()[:max_length]

    words = re.findall(r'\w+', message)
    if words:
        title = ' '.join(words[:5])
        if len(title) > max_length:
            title = title[:max_length - 3] + "..."
        return title

    return "New chat"


def generate_title_from_context(
    user_message: str,
    assistant_response: Optional[str] = None,
    circuit_name: Optional[str] = None,
) -> str:
    """Prefer explicit ``circuit_name``, then heuristics over user + assistant text."""
    if circuit_name:
        return f"Circuit {circuit_name}"[:40]

    title = generate_session_title(user_message)

    if assistant_response and title == "New chat":
        module_pattern = r'module\s*[：:]\s*([a-zA-Z0-9_]+)'
        match = re.search(module_pattern, assistant_response, re.IGNORECASE)
        if match:
            return f"Circuit {match.group(1)}"[:40]

        function_pattern = r'(?:this is|implements?)\s*([^\n.,]{5,30})'
        match = re.search(function_pattern, assistant_response, re.IGNORECASE)
        if match:
            description = match.group(1).strip()
            return description[:40]

    return title


if __name__ == "__main__":
    test_cases = [
        "/reverse adder.aig",
        "Analyze this adder circuit",
        "module counter(input clk, output [7:0] count);",
        "Help me optimize area for this design",
        "How is timing for this block?",
        "Please run logic synthesis",
        "verify the design",
        "analyze timing for cpu_core.v",
        "This is a very long message that should be truncated sensibly so the title stays within limits",
        "hi",
    ]

    print("Session title smoke test:\n")
    for i, msg in enumerate(test_cases, 1):
        title = generate_session_title(msg)
        print(f"{i}. message: {msg[:50]}")
        print(f"   title: {title}\n")
