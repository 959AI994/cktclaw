#!/usr/bin/env python3
"""
Qwen 本地模型真实调用测试
测试：模型加载、基础对话、工具调用解析、CktClaw provider 集成
"""

import sys, os, asyncio, json

os.chdir('/root/cktclaw')
sys.path.insert(0, '/root')

MODEL_PATH = '/root/cktclaw/models/qwen/Qwen2.5-3B'
PASS = "✅"; FAIL = "❌"
results = []

def check(name, ok, detail=""):
    results.append((PASS if ok else FAIL, name))
    print(f"  {PASS if ok else FAIL} {name}" + (f": {detail}" if detail else ""))

print("=" * 70)
print("Qwen2.5-3B 本地模型真实调用测试")
print("=" * 70)

# ── Test 1: 模型文件完整性 ──────────────────────────────────
print("\n[1] 模型文件完整性检查")
required = ['config.json', 'tokenizer.json', 'tokenizer_config.json',
            'model-00001-of-00002.safetensors', 'model-00002-of-00002.safetensors']
for f in required:
    path = os.path.join(MODEL_PATH, f)
    size = os.path.getsize(path) if os.path.exists(path) else 0
    check(f, size > 0, f"{size/1e9:.2f}GB" if size > 1e8 else f"{size} bytes")

# ── Test 2: CktClaw config 集成 ─────────────────────────────
print("\n[2] CktClaw config 集成测试")
os.environ['CKTCLAW_LOCAL_MODEL'] = MODEL_PATH
import importlib
import cktclaw.config as cfg
importlib.reload(cfg)
check("CODEV_PATH 指向 Qwen 模型", cfg.CODEV_PATH == MODEL_PATH, cfg.CODEV_PATH)

# ── Test 3: LocalCodeVProvider 加载 ────────────────────────
print("\n[3] LocalCodeVProvider 加载测试（CPU 模式）")
try:
    from cktclaw.models.providers.local_codev_provider import LocalCodeVProvider
    # 强制 CPU（gpu_id=-1 跳过 GPU 选择）
    provider = LocalCodeVProvider(codev_path=MODEL_PATH, gpu_id=-1, verbose=False)
    # 手动加载（绕过 GPU 检查）
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch

    provider._tokenizer = AutoTokenizer.from_pretrained(MODEL_PATH, trust_remote_code=True)
    provider._model = AutoModelForCausalLM.from_pretrained(
        MODEL_PATH, dtype=torch.float32, device_map='cpu', trust_remote_code=True
    )
    provider._model.eval()
    provider._loaded = True
    provider.device = 'cpu'
    check("LocalCodeVProvider 初始化", True)
    check("模型加载到 CPU", str(next(provider._model.parameters()).device) == 'cpu',
          str(next(provider._model.parameters()).device))
except Exception as e:
    check("LocalCodeVProvider 加载", False, str(e))
    provider = None

# ── Test 4: 基础对话 ────────────────────────────────────────
print("\n[4] 本地模型基础对话测试")
if provider:
    try:
        resp = provider.chat_with_context([
            {"role": "user", "content": "AIG 是什么？用一句话回答。"}
        ])
        ok = isinstance(resp, str) and len(resp) > 5
        check("基础对话", ok, resp[:100] if ok else str(resp)[:100])
    except Exception as e:
        check("基础对话", False, str(e))

# ── Test 5: 工具调用解析 ────────────────────────────────────
print("\n[5] 工具调用解析测试（ToolCallParser）")
try:
    from cktclaw.utils.tool_call_parser import ToolCallParser
    parser = ToolCallParser(verbose=False)

    # 模拟模型输出包含工具调用的文本
    fake_output = '''{"type": "tool_call", "name": "yosys", "arguments": {"args": "read_aiger test.aig; stat"}}'''
    result = parser.parse(fake_output)
    check("JSON 格式工具调用解析", result is not None and result.get("name") == "yosys",
          str(result)[:80] if result else "None")
except Exception as e:
    check("工具调用解析", False, str(e))

# ── Test 6: 多轮对话 ────────────────────────────────────────
print("\n[6] 本地模型多轮对话测试")
if provider:
    try:
        messages = [
            {"role": "user", "content": "你好"},
            {"role": "assistant", "content": "你好！我是 CktClaw EDA 助手。"},
            {"role": "user", "content": "什么是逻辑综合？"}
        ]
        resp = provider.chat_with_context(messages)
        ok = isinstance(resp, str) and len(resp) > 10
        check("多轮对话", ok, resp[:100] if ok else str(resp)[:100])
    except Exception as e:
        check("多轮对话", False, str(e))

# ── Summary ────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for s, _ in results if s == PASS)
failed = sum(1 for s, _ in results if s == FAIL)
print(f"测试结果: {passed} 通过 / {failed} 失败 / {len(results)} 总计")
if failed == 0:
    print("🎉 Qwen 本地模型测试全部通过！")
else:
    print("⚠️  部分测试失败，请检查上方输出。")
print("=" * 70)
print()
print("使用方法：")
print(f"  export CKTCLAW_LOCAL_MODEL={MODEL_PATH}")
print("  conda run -n logic python main.py")
print("  # 在 CktClaw 中输入 /model 选择 logicrt（本地模型）")
