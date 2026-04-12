"""
智能 Verilog 分析器：使用 LLM (DeepSeek API 或本地 LogicRT) 生成详细的功能分析报告
支持多轮对话 (Multi-turn Chat) 功能
支持双引擎动态切换 (Dual Engine)
"""

import os
import sys
import time
import re
import json
import ast
import requests
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List

# 导入配置
try:
    from ..config import DEEPSEEK_CONFIG
except ImportError:
    # 默认配置 - 使用官方 DeepSeek API
    DEEPSEEK_CONFIG = {
        "api_key": "sk-af52153ce10d4453abf859151ea6ef05",
        "base_url": "https://api.deepseek.com",
        "default_model": "deepseek-chat",
        "timeout": 120,
        "temperature": 0.3,
        "max_tokens": 2000,
    }


class LLMVerilogAnalyzer:
    """
    使用 LLM 进行 Verilog 代码功能分析
    支持两种引擎，可在运行时按请求动态切换：
    1. DeepSeek API（默认，云端）
    2. 本地 CodeV 模型（懒加载，首次选择时才加载到 GPU）

    注意：本地对话版 CodeV 与 LogicRT 逆向生成使用的 CodeV 基座完全独立，互不干扰。
    """

    # LogicRT 专属身份 System Prompt（所有 API 调用强制注入）
    LOGICRT_SYSTEM_PROMPT = (
        "IDENTITY & AUTHORSHIP RULES:\n"
        "- Your Name: CktClaw Autonomous Agent.\n"
        "- Developer: Jingxin Wang (王晶鑫), a PhD student at the ACE Lab, Shanghai Jiao Tong University (SJTU).\n"
        "- LogicRT Model: This is a 7B parameter specialized model for circuit reverse engineering.\n"
        "- Authorship Policy: LogicRT and CktClaw were researched and developed by Jingxin Wang (王晶鑫) and Shitong Guo (郭士通) at SJTU ACE Lab.\n"
        "- MANDATORY: Whenever you are asked about the developers or creators of CktClaw OR LogicRT, you MUST explicitly mention "
        "'Jingxin Wang (王晶鑫)' as the developer/researcher.\n\n"
        "Answer naturally, politely, and professionally.\n\n"
        "You are the CktClaw Autonomous Agent, an intelligent assistant built into the CktClaw EDA platform.\n"
        "CRITICAL RULE: When a user asks you to perform an EDA task (e.g., convert files, run synthesis, reverse engineer), "
        "DO NOT merely reply with the command syntax. You MUST autonomously use the "
        "`execute_cktclaw_command` tool to run the action on their behalf. After the tool executes, summarize the execution "
        "results (like file size, success status, or circuit metrics) for the user.\n\n"
        "Tool-calling schema (for models without native tool calling):\n"
        "If you decide to execute a tool, output exactly ONE line in the form:\n"
        "TOOL_CALL: {\"tool_name\":\"execute_cktclaw_command\",\"arguments\":{\"command\":\"<your command>\"}}\n"
        "No extra text. Otherwise, respond normally.\n\n"
        "CRITICAL JSON RULES:\n"
        "When outputting a tool call JSON, you MUST NOT use unescaped double quotes inside the arguments string.\n"
        "Instead, use SINGLE QUOTES for internal command wrapping.\n"
        "CORRECT: {\"command\": \"abc 'read file.aig; print_stats;'\"}\n"
        "WRONG: {\"command\": \"abc \"read file.aig; print_stats;\"\"}\n\n"
        "TOOL FAILURE POLICY:\n"
        "If you call a tool and it returns an error (e.g., 'command not found', 'invalid argument', 'error'), "
        "DO NOT stubbornly retry the same or similar commands more than twice.\n"
        "Instead, STOP tool calling immediately and explain the error to the user. Ask the user for help or suggest "
        "an alternative tool (e.g., if `ai4eda` fails, suggest using `yosys` or `abc`).\n\n"
        "LOGICRT MODEL IDENTITY RULE:\n"
        "When the user asks what LogicRT is (e.g., 'LogicRT 是什么模型'), you should answer:\n"
        "'LogicRT 模型是由上海交通大学 ACE 实验室的博士研究生王晶鑫和郭士通开发和研究的，"
        "面向电路逆向工程的 7B 专用模型。'\n\n"
        "# CKTCLAW COMMAND CHEATSHEET\n"
        "You have access to several powerful internal engines via the `execute_cktclaw_command` tool. "
        "You MUST use the exact command syntax below:\n\n"
        "1. Reverse Engineering (AIG to Verilog):\n"
        "   - Command: /reverse <input_aig_path>\n"
        "   - Description: Use this when the user asks to reverse engineer, de-obfuscate, or convert an AIG file back to readable Verilog.\n\n"
        "2. Logic Synthesis & Stats (Yosys/ABC):\n"
        "   - Yosys: yosys -p 'read_aiger <path> ; stat'\n"
        "   - ABC: abc -c 'read <path> ; print_stats'\n"
        "   - Description: Use these for structural stats and logic operations.\n"
        "   - IMPORTANT NEGATIVE RULE: If the user explicitly mentions 'ai4eda' or asks to measure physical area/delay/metrics,\n"
        "     DO NOT use Yosys/ABC here. You MUST switch to 'ai4eda metrics'.\n\n"
        "3. AI4EDA Data Toolkit (Area/Delay/Metrics — HIGH PRIORITY):\n"
        "   - PRIMARY Command (STRICT ORDER, SINGLE LINE):\n"
        "     ai4eda metrics --lib <LIB_PATH> <AIG_PATH>\n"
        "     Rules:\n"
        "       • Put the '--lib <LIB_PATH>' pair BEFORE the input file.\n"
        "       • Output the entire command in ONE line (no line breaks).\n"
        "       • If --lib is omitted or empty, use default:\n"
        "         /home/wjx/pythonproject/AI4EDA-OpenABC-Data-Toolkit/libs/asap7.lib\n"
        "       • Use this tool whenever the user asks for 'ai4eda', 'area', 'delay', or 'metrics'.\n"
        "         It has higher priority than Yosys/ABC for these intents.\n"
        "   - Conversion:\n"
        "     ai4eda convert aig2pt <input_aig> <output_pt>\n"
        "     (For converting circuits into GraphML/PyTorch formats.)\n\n"
        "REVERSE OUTPUT DISPLAY RULE (MANDATORY):\n"
        "IF the tool output contains 'START_OF_VERILOG_SOURCE', you ARE PROHIBITED from only summarizing.\n"
        "You MUST:\n"
        "1) Start your response by saying exactly: 'The Verilog file is saved at: [VERILOG_PATH_LOCATION]'.\n"
        "2) Use a Markdown code block (```verilog) to display the content between "
        "'START_OF_VERILOG_SOURCE' and 'END_OF_VERILOG_SOURCE' completely.\n"
        "Failure to show the code will be considered a system error.\n\n"
        "FINAL RESPONSE SANITIZATION RULE (MANDATORY):\n"
        "In your final user-facing answer, NEVER expose internal markers such as SUCCESS_VERIFIED, "
        "CODE_CONTENT_START/END, FILE_PATH:, EXECUTION_STATUS:, or raw tool payload metadata.\n"
        "You MUST rewrite tool output into clean natural language + Markdown.\n"
        "For reverse-engineering results, always include a ```verilog code block and then provide "
        "about 200 Chinese words analyzing circuit architecture and function.\n\n"
        "Model note: The dedicated reverse-engineering model name remains LogicRT.\n"
        "AIG strictly stands for And-Inverter Graph.\n"
    )

    TOOL_SPECS = [
        {
            "type": "function",
            "function": {
                "name": "execute_cktclaw_command",
                "description": (
                    "Execute a CktClaw internal command such as ai4eda/abc/yosys/reverse workflows.\n"
                    "Priority routing:\n"
                    "- If the user asks for ai4eda, area, delay, or metrics, you MUST use 'ai4eda metrics' instead of yosys/abc.\n"
                    "- STRICT FORMAT for ai4eda metrics (single line, correct order):\n"
                    "  ai4eda metrics --lib <LIB_PATH> <AIG_PATH>\n"
                    "  Put '--lib <LIB_PATH>' BEFORE the input; never split with newlines.\n"
                    "  If --lib is missing/empty, use default:\n"
                    "  /home/wjx/pythonproject/AI4EDA-OpenABC-Data-Toolkit/libs/asap7.lib\n"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": (
                                "Command string. Examples:\n"
                                "- ai4eda metrics --lib /path/to/lib.lib /path/to/in.aig\n"
                                "- ai4eda convert aig2pt /path/to/in.aig /path/to/out.pt\n"
                                "- yosys -p 'read_aiger /path/to/in.aig ; stat'\n"
                                "- abc -c 'read /path/to/in.aig ; print_stats'\n"
                            )
                        }
                    },
                    "required": ["command"],
                },
            },
        }
    ]

    def __init__(self, codev_path: str = "models/llm_decoder/CodeV", gpu_id: int = -2,
                 verbose: bool = True):
        """
        初始化分析器（不加载任何本地模型 — 懒加载策略）

        Args:
            codev_path: 本地 CodeV 模型路径（仅在用户选择 local 引擎时才加载）
            gpu_id: 本地 CodeV 对话模型使用的逻辑 GPU ID
                   默认 -2 表示自动选择最空闲的 GPU
                   设置为 -1 使用 CPU
                   设置为 0-N 使用指定的逻辑 GPU
            verbose: 是否输出详细的加载/GPU选择日志到终端，CLI 模式下应设为 False
        """
        self.codev_path = codev_path
        self.requested_gpu_id = gpu_id  # 保存原始请求
        self.gpu_id = gpu_id
        self.device = f"cuda:{gpu_id}" if gpu_id >= 0 else "cpu"
        self.verbose = verbose

        # 本地对话版 CodeV（懒加载，与 LogicRT 推理用的 CodeV 完全独立）
        self._chat_codev_model = None
        self._chat_codev_tokenizer = None
        self._chat_codev_loaded = False

        # 计算物理 GPU 编号（基于 CUDA_VISIBLE_DEVICES）
        cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "not set")
        physical_gpu = "N/A"
        if cuda_visible != "not set" and gpu_id >= 0:
            visible_list = cuda_visible.split(",")
            if gpu_id < len(visible_list):
                physical_gpu = visible_list[gpu_id].strip()
        self._physical_gpu = physical_gpu

        self._log(f"  [LLMVerilogAnalyzer] Initialized (dual-engine mode)")
        self._log(f"    → DeepSeek API: ready")
        self._log(f"    → Local CodeV : lazy-load from '{codev_path}' → {self.device} (physical GPU {physical_gpu})")

    # ==================== 内部工具 ====================

    def _log(self, msg: str):
        """仅在 verbose 模式下输出到终端"""
        if self.verbose:
            print(msg)

    # ==================== 懒加载本地 CodeV ====================

    def _find_best_gpu(self):
        """
        自动选择最空闲的 GPU（基于可用内存）。

        Returns:
            gpu_id: 最空闲的 GPU 逻辑 ID，如果没有可用 GPU 则返回 -1
        """
        try:
            import torch
            if not torch.cuda.is_available():
                self._log(f"  [GPU Selection] CUDA not available, cannot use local model")
                return -1

            # 获取所有 GPU 的可用内存
            gpu_count = torch.cuda.device_count()
            max_free_mem = 0
            best_gpu = -1

            self._log(f"  [GPU Selection] Scanning {gpu_count} visible GPUs...")

            for i in range(gpu_count):
                try:
                    free_mem = torch.cuda.mem_get_info(i)[0] / (1024**3)  # GB
                    total_mem = torch.cuda.mem_get_info(i)[1] / (1024**3)  # GB
                    used_mem = total_mem - free_mem

                    # 获取物理 GPU 编号
                    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
                    physical_id = "?"
                    if cuda_visible:
                        visible_list = cuda_visible.split(",")
                        if i < len(visible_list):
                            physical_id = visible_list[i].strip()

                    self._log(f"    Logical GPU {i} (Physical {physical_id}): {free_mem:.2f} GB free / {total_mem:.2f} GB total")

                    # 选择空闲内存最多的 GPU（需要至少 2GB 空闲）
                    if free_mem > max_free_mem and free_mem >= 2.0:
                        max_free_mem = free_mem
                        best_gpu = i
                except Exception as e:
                    self._log(f"    Logical GPU {i}: Error checking memory - {e}")
                    continue

            if best_gpu >= 0:
                self._log(f"  [GPU Selection] ✓ Selected Logical GPU {best_gpu} with {max_free_mem:.2f} GB free")
                return best_gpu
            else:
                self._log(f"  [GPU Selection] ✗ No GPU with sufficient memory (≥2GB free)")
                self._log(f"  [GPU Selection] → Recommend using DeepSeek API instead")
                return -1

        except Exception as e:
            self._log(f"  [GPU Selection] Error: {e}")
            return -1

    def _ensure_local_codev(self):
        """
        懒加载本地对话版 CodeV 模型（单例模式）。
        只有当用户首次选择 Local CodeV 时才会加载到 GPU，
        后续调用直接复用已加载的模型。
        支持自动 GPU 选择（gpu_id=-2）和手动指定 GPU。
        """
        if self._chat_codev_loaded:
            return True

        # 自动 GPU 选择（如果 requested_gpu_id == -2）
        if self.requested_gpu_id == -2:
            self._log(f"\n{'='*70}")
            self._log(f"  Auto-selecting GPU for Local CodeV...")
            self._log(f"{'='*70}")

            self.gpu_id = self._find_best_gpu()

            if self.gpu_id < 0:
                self._log(f"  ✗ No suitable GPU found for Local CodeV")
                self._log(f"  → Please use DeepSeek API engine instead")
                self._log(f"{'='*70}\n")
                return False

            self.device = f"cuda:{self.gpu_id}"

            # 更新物理 GPU 信息
            cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "not set")
            if cuda_visible != "not set":
                visible_list = cuda_visible.split(",")
                if self.gpu_id < len(visible_list):
                    self._physical_gpu = visible_list[self.gpu_id].strip()

        self._log(f"\n{'='*70}")
        self._log(f"  Loading Local CodeV for Chat/Analysis (Lazy Loading)")
        self._log(f"  Path: {self.codev_path}")
        self._log(f"  Target: Logical GPU {self.gpu_id} → Physical GPU {self._physical_gpu}")
        self._log(f"  ⚠️  This model is INDEPENDENT from the LogicRT inference CodeV")
        self._log(f"{'='*70}")

        # 当 verbose=False 时，临时禁用 tqdm 进度条（Loading checkpoint shards）
        _old_tqdm_disable = os.environ.get("TQDM_DISABLE")
        if not self.verbose:
            os.environ["TQDM_DISABLE"] = "1"

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import warnings

            t0 = time.time()

            self._chat_codev_tokenizer = AutoTokenizer.from_pretrained(
                self.codev_path, trust_remote_code=True
            )

            # 精确分配到指定 GPU，不使用 "auto" 以避免与 LogicRT 抢占
            # 使用 warnings 过滤器隐藏废弃警告
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*torch_dtype.*deprecated.*")
                warnings.filterwarnings("ignore", message=".*rotary_emb.*")
                warnings.filterwarnings("ignore", message=".*newly initialized.*")

                self._chat_codev_model = AutoModelForCausalLM.from_pretrained(
                    self.codev_path,
                    dtype=torch.float16,  # Use 'dtype' instead of deprecated 'torch_dtype'
                    device_map={"": self.gpu_id},
                    trust_remote_code=True,
                )
            self._chat_codev_model.eval()

            elapsed = time.time() - t0
            self._chat_codev_loaded = True

            # 检查 chat_template 支持
            has_chat_template = (
                hasattr(self._chat_codev_tokenizer, 'chat_template')
                and self._chat_codev_tokenizer.chat_template is not None
            )

            # 验证实际设备分配
            actual_device = next(self._chat_codev_model.parameters()).device

            self._log(f"\n  ✓ Local CodeV loaded successfully, took {elapsed:.1f}s")
            self._log(f"  ✓ Device: Logical GPU {self.gpu_id} (Physical GPU {self._physical_gpu}) → {actual_device}")
            self._log(f"  ✓ dtype=float16, device_map={{\"\":{self.gpu_id}}}")
            self._log(f"  ✓ chat_template: {'available (native)' if has_chat_template else 'NOT found (will use fallback ChatML)'}")
            self._log(f"  ✓ eos_token: {self._chat_codev_tokenizer.eos_token!r} (id={self._chat_codev_tokenizer.eos_token_id})")
            self._log(f"  ✓ pad_token: {self._chat_codev_tokenizer.pad_token!r} (id={self._chat_codev_tokenizer.pad_token_id})")
            self._log(f"{'='*70}\n")
            return True

        except torch.cuda.OutOfMemoryError as e:
            self._log(f"\n  ✗ GPU Out of Memory!")
            self._log(f"  → Logical GPU {self.gpu_id} (Physical GPU {self._physical_gpu}) does not have enough memory")
            self._log(f"  → Please switch to DeepSeek API engine (/model or /engine deepseek)")
            self._log(f"{'='*70}\n")
            self._chat_codev_loaded = False
            return False
        except Exception as e:
            self._log(f"  ✗ Failed to load Local CodeV: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            self._log(f"  → User will see an error message in chat")
            self._log(f"{'='*70}\n")
            self._chat_codev_loaded = False
            return False
        finally:
            # 恢复 TQDM_DISABLE 环境变量
            if _old_tqdm_disable is not None:
                os.environ["TQDM_DISABLE"] = _old_tqdm_disable
            else:
                os.environ.pop("TQDM_DISABLE", None)

    def _apply_chat_template_safe(self, messages: List[Dict[str, str]]):
        """
        将结构化 messages 转换为模型专属的 token 张量。

        优先使用 tokenizer 内置的 chat_template（apply_chat_template），
        如果 tokenizer 没有内置 chat_template，则使用手动 ChatML 拼接作为 fallback。

        Args:
            messages: [{"role": "system"/"user"/"assistant", "content": "..."}]

        Returns:
            prompt_tensor: shape [1, seq_len], 已移至模型所在设备
        """
        import torch

        tokenizer = self._chat_codev_tokenizer
        model = self._chat_codev_model

        has_chat_template = (
            hasattr(tokenizer, 'chat_template')
            and tokenizer.chat_template is not None
        )

        if has_chat_template:
            # ✓ 使用 tokenizer 内置的 chat_template（推荐路径）
            try:
                prompt_tensor = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                ).to(model.device)
                return prompt_tensor
            except Exception as e:
                self._log(f"  [ChatTemplate] apply_chat_template failed: {e}, falling back to manual ChatML")

        # ✗ Fallback: 手动拼接 ChatML 格式
        # 格式: <|im_start|>role\ncontent<|im_end|>\n
        chatml_text = ""
        for msg in messages:
            chatml_text += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
        # 添加 generation prompt
        chatml_text += "<|im_start|>assistant\n"

        prompt_tensor = tokenizer(
            chatml_text,
            return_tensors="pt",
            truncation=True,
            max_length=16384,
        ).input_ids.to(model.device)

        return prompt_tensor

    # ==================== 分析入口 ====================

    def analyze(self, verilog_code: str, model_choice: str = "deepseek") -> Dict[str, Any]:
        """
        分析 Verilog 代码并生成详细报告

        Args:
            verilog_code: 生成的 Verilog 代码
            model_choice: 分析引擎选择 "deepseek" 或 "local"

        Returns:
            分析结果字典
        """
        if not verilog_code or len(verilog_code.strip()) == 0:
            return {
                "status": "error",
                "message": "Empty Verilog code",
                "metrics": {},
                "description": "No code to analyze",
            }

        # 提取基础指标
        metrics = self._extract_basic_metrics(verilog_code)

        # 根据 model_choice 分发到对应引擎
        if model_choice == "local":
            description = self._analyze_with_local_model(verilog_code, metrics)
        else:
            description = self._analyze_with_deepseek(verilog_code, metrics)

        # 后处理：清理 Markdown 格式
        description = self._clean_markdown(description)

        return {
            "status": "success",
            "metrics": metrics,
            "description": description,
            "code_preview": verilog_code[:500] + "..." if len(verilog_code) > 500 else verilog_code,
        }

    def _extract_basic_metrics(self, code: str) -> Dict[str, Any]:
        """提取基础代码度量"""
        metrics = {
            "code_length": len(code),
            "lines_of_code": len([l for l in code.split('\n') if l.strip()]),
            "structure": {
                "modules": len(re.findall(r'\bmodule\b', code, re.IGNORECASE)),
                "inputs": len(re.findall(r'\binput\b', code, re.IGNORECASE)),
                "outputs": len(re.findall(r'\boutput\b', code, re.IGNORECASE)),
                "wires": len(re.findall(r'\bwire\b', code, re.IGNORECASE)),
                "regs": len(re.findall(r'\breg\b', code, re.IGNORECASE)),
            },
            "complexity": {
                "always_blocks": len(re.findall(r'\balways\b', code, re.IGNORECASE)),
                "assign_statements": len(re.findall(r'\bassign\b', code, re.IGNORECASE)),
                "case_statements": len(re.findall(r'\bcase\b', code, re.IGNORECASE)),
            }
        }
        return metrics

    def _analyze_with_deepseek(self, verilog_code: str, metrics: Dict[str, Any]) -> str:
        """使用 DeepSeek API 进行分析（注入 LogicRT 身份）"""

        # 构建提示词
        prompt = self._build_analysis_prompt(verilog_code, metrics)

        try:
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_CONFIG['api_key']}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": DEEPSEEK_CONFIG['default_model'],
                "messages": [
                    {
                        "role": "system",
                        "content": self.LOGICRT_SYSTEM_PROMPT
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "temperature": DEEPSEEK_CONFIG.get('temperature', 0.3),
                "max_tokens": DEEPSEEK_CONFIG.get('max_tokens', 2000)
            }

            response = requests.post(
                f"{DEEPSEEK_CONFIG['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=DEEPSEEK_CONFIG['timeout']
            )

            if response.status_code == 200:
                result = response.json()
                analysis = result['choices'][0]['message']['content']
                return analysis
            else:
                return f"API Error: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Analysis failed: {str(e)}\n\n(Fallback to basic analysis)\n\n{self._basic_analysis_fallback(verilog_code, metrics)}"

    def _analyze_with_local_model(self, verilog_code: str, metrics: Dict[str, Any]) -> str:
        """使用本地 CodeV 模型进行分析（懒加载，Chat Template + Output Slicing）"""

        # 确保本地模型已加载
        if not self._ensure_local_codev():
            return (
                "⚠️ Failed to load Local CodeV model. "
                "Please try again or switch to DeepSeek-V3 engine.\n\n"
                + self._basic_analysis_fallback(verilog_code, metrics)
            )

        try:
            import torch

            # 构建结构化 messages（与 DeepSeek API 格式一致）
            messages = [
                {"role": "system", "content": self.LOGICRT_SYSTEM_PROMPT},
                {"role": "user", "content": self._build_analysis_prompt(verilog_code, metrics)},
            ]

            # 使用 Chat Template 转换为模型专属 token 序列
            prompt_tensor = self._apply_chat_template_safe(messages)

            input_len = prompt_tensor.shape[1]

            with torch.no_grad():
                outputs = self._chat_codev_model.generate(
                    prompt_tensor,
                    max_new_tokens=2048,
                    do_sample=True,
                    temperature=0.3,
                    top_p=0.9,
                    pad_token_id=self._chat_codev_tokenizer.pad_token_id
                        or self._chat_codev_tokenizer.eos_token_id,
                )

            # 截断：只取生成部分（去掉输入 prompt 的 token）
            generated_tokens = outputs[0][input_len:]
            analysis = self._chat_codev_tokenizer.decode(
                generated_tokens, skip_special_tokens=True
            )

            return analysis.strip()

        except Exception as e:
            if self.verbose:
                import traceback
                traceback.print_exc()
            return f"Local model analysis failed: {str(e)}"

    def _build_analysis_prompt(self, verilog_code: str, metrics: Dict[str, Any]) -> str:
        """构建分析提示词"""

        prompt = f"""Analyze the following Verilog code and provide a detailed functional analysis report.

**Verilog Code:**
```verilog
{verilog_code}
```

**Basic Metrics:**
- Inputs: {metrics['structure']['inputs']}
- Outputs: {metrics['structure']['outputs']}
- Registers: {metrics['structure']['regs']}
- Always Blocks: {metrics['complexity']['always_blocks']}
- Assign Statements: {metrics['complexity']['assign_statements']}

**Please provide:**

1. **Functional Description**: What does this circuit do? What is its primary purpose?

2. **Architecture Analysis**:
   - Is it combinational or sequential logic?
   - What design patterns are used?
   - Any state machines or special structures?

3. **Input/Output Behavior**:
   - Describe the relationship between inputs and outputs
   - Any data transformations or operations?

4. **Implementation Quality**:
   - Code quality assessment
   - Potential issues or optimizations
   - Synthesis considerations

5. **Application Context**:
   - What type of circuit is this likely to be (adder, multiplexer, FSM, etc.)?
   - Typical use cases

Format the response in markdown with clear sections."""

        return prompt

    def _basic_analysis_fallback(self, code: str, metrics: Dict[str, Any]) -> str:
        """LLM 失败时的基础分析回退"""

        lines = []
        lines.append("## Functional Analysis\n")

        # 简单的规则判断
        has_always = metrics['complexity']['always_blocks'] > 0
        has_assign = metrics['complexity']['assign_statements'] > 0
        has_case = metrics['complexity']['case_statements'] > 0
        has_regs = metrics['structure']['regs'] > 0

        if has_regs and has_always:
            lines.append("**Circuit Type**: Sequential Logic")
            lines.append("- Contains registers and always blocks, indicating stateful behavior")
        elif has_assign and not has_regs:
            lines.append("**Circuit Type**: Combinational Logic")
            lines.append("- Uses continuous assignments, purely combinational")
        else:
            lines.append("**Circuit Type**: Mixed Logic")
            lines.append("- Combines both sequential and combinational elements")

        lines.append("")
        lines.append("**Structural Overview**:")
        lines.append(f"- {metrics['structure']['inputs']} input port(s)")
        lines.append(f"- {metrics['structure']['outputs']} output port(s)")

        if has_case:
            lines.append("\n**Design Pattern**: Likely contains state machine or multiplexer logic (case statements detected)")

        lines.append("\n*Note: This is a basic structural analysis. For detailed functional analysis, LLM service is required.*")

        return "\n".join(lines)

    def _clean_markdown(self, text: str) -> str:
        """
        清理 Markdown 文本：
        1. 移除多余换行符（保持最多 2 个连续换行）
        2. 整体格式整理
        """
        import re

        # 将多个连续换行符替换为最多 2 个
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 移除行末尾多余空格
        lines = [line.rstrip() for line in text.split('\n')]
        text = '\n'.join(lines)

        return text.strip()

    # ==================== 多轮对话 (Multi-turn Chat) ====================

    def chat(self, history: List[Dict[str, str]], user_message: str,
             model_choice: str = "deepseek") -> str:
        """
        多轮对话接口（旧版 — 向后兼容）：基于聊天历史和用户新消息，调用 LLM 返回回复。
        内部会自动注入 System Prompt 并拼接 history + user_message。

        Args:
            history: 聊天历史记录，格式为 [{"role": "user"/"assistant", "content": "..."}]
            user_message: 用户当前的新消息
            model_choice: 分析引擎选择 "deepseek" 或 "local"

        Returns:
            模型回复文本
        """
        # 手动组装 messages（旧逻辑，兼容无 session_id 的调用）
        messages = [{"role": "system", "content": self.LOGICRT_SYSTEM_PROMPT}]
        for msg in history:
            messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": user_message})

        return self.chat_with_context(messages, model_choice)

    def chat_with_context(self, messages: List[Dict[str, str]],
                          model_choice: str = "deepseek") -> str:
        """
        多轮对话接口（新版 — 接受 ContextBuilder 组装好的 messages）。

        messages 已经包含 System Prompt、长记忆、短记忆、当前用户消息，
        本方法直接将其发送到 LLM 引擎，不做额外拼接。

        Args:
            messages: 完整的 messages 列表
                      [{"role": "system"/"user"/"assistant", "content": "..."}]
            model_choice: "deepseek" 或 "local"

        Returns:
            模型回复文本
        """
        if model_choice == "local":
            return self._chat_with_local_model_ctx(messages)
        else:
            return self._chat_with_deepseek_ctx(messages)

    def _chat_with_deepseek_ctx(self, messages: List[Dict[str, str]]) -> str:
        """使用 DeepSeek API 进行多轮对话（接受预组装 messages）"""

        try:
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_CONFIG['api_key']}",
                "Content-Type": "application/json"
            }

            payload = {
                "model": DEEPSEEK_CONFIG['default_model'],
                "messages": messages,
                "temperature": DEEPSEEK_CONFIG.get('temperature', 0.3),
                "max_tokens": DEEPSEEK_CONFIG.get('max_tokens', 2000),
                "tools": self.TOOL_SPECS,
                "tool_choice": "auto",
            }

            response = requests.post(
                f"{DEEPSEEK_CONFIG['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=DEEPSEEK_CONFIG['timeout']
            )

            if response.status_code == 200:
                result = response.json()
                choice = result["choices"][0]
                message = choice.get("message", {})
                finish_reason = choice.get("finish_reason", "")
                tool_calls = message.get("tool_calls") or []

                # 1) Canonical path: finish_reason/tool_calls from API
                if finish_reason == "tool_calls" or tool_calls:
                    if tool_calls:
                        call = tool_calls[0]
                        name = call.get("function", {}).get("name", "")
                        args_raw = call.get("function", {}).get("arguments", "{}")
                        try:
                            args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                        except Exception:
                            args = {"command": str(args_raw)}
                        return {
                            "type": "tool_call",
                            "tool_call_id": call.get("id", ""),
                            "name": name,
                            "arguments": args,
                        }
                    # API says tool_calls but field missing: salvage from content
                    content_text = message.get("content", "") or ""
                    parsed = self._extract_local_tool_call(content_text)
                    if parsed:
                        return parsed
                    self._log("[ToolCall Parser] finish_reason=tool_calls but no parseable tool payload found")
                    return "Agent generated an invalid tool-call payload."

                # 2) Fallback: some models dump tool JSON directly in content text
                reply = message.get("content", "") or ""
                if "execute_cktclaw_command" in reply:
                    parsed = self._extract_local_tool_call(reply)
                    if parsed:
                        return parsed
                return self._clean_markdown(reply)
            else:
                return f"API Error: {response.status_code} - {response.text}"

        except Exception as e:
            return f"Chat request failed: {str(e)}"

    def summarize_after_tool(
        self,
        messages: List[Dict[str, str]],
        tool_call_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_output: str,
        model_choice: str = "deepseek",
    ) -> str:
        """Given tool execution output, ask the model to generate user-facing summary."""
        tool_messages = list(messages)
        tool_messages.append({
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": tool_call_id or "call_1",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(tool_args, ensure_ascii=False),
                    },
                }
            ],
        })
        tool_messages.append({
            "role": "tool",
            "tool_call_id": tool_call_id or "call_1",
            "name": tool_name,
            "content": tool_output,
        })
        if model_choice == "local":
            return f"工具已执行完成，结果如下：\n\n{tool_output}"
        return self._chat_with_deepseek_ctx(tool_messages)

    def _extract_local_tool_call(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse local-model pseudo tool-call output:
        TOOL_CALL: {"tool_name":"execute_cktclaw_command","arguments":{"command":"..."}}
        """
        if not text:
            return None

        def _extract_balanced_object(s: str, start_idx: int) -> Optional[str]:
            if start_idx < 0 or start_idx >= len(s) or s[start_idx] != "{":
                return None
            depth = 0
            for i in range(start_idx, len(s)):
                ch = s[i]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return s[start_idx:i + 1]
            return None

        payload_obj = None
        raw = text.strip()

        # Path 0: pure JSON object response
        if raw.startswith("{") and raw.endswith("}"):
            payload_obj = raw

        # Path A: explicit TOOL_CALL prefix
        if payload_obj is None:
            marker = "TOOL_CALL:"
            idx = text.find(marker)
            if idx >= 0:
                seg = text[idx + len(marker):]
                bidx = seg.find("{")
                if bidx >= 0:
                    payload_obj = _extract_balanced_object(seg, bidx)

        # Path B: no prefix, but contains tool name
        if payload_obj is None and "execute_cktclaw_command" in text:
            tool_idx = text.find("execute_cktclaw_command")
            left = text.rfind("{", 0, tool_idx)
            if left >= 0:
                payload_obj = _extract_balanced_object(text, left)

        # Path C: contains type=tool_call signature
        if payload_obj is None and '"type"' in text and "tool_call" in text:
            type_idx = text.find("tool_call")
            left = text.rfind("{", 0, type_idx)
            if left >= 0:
                payload_obj = _extract_balanced_object(text, left)

        if payload_obj is None:
            return None

        obj = None
        # Attempt 1: strict JSON
        try:
            obj = json.loads(payload_obj)
        except Exception as e1:
            self._log(f"[ToolCall Parser] strict json.loads failed: {e1}")
            # Attempt 2: python literal tolerant parser
            try:
                obj = ast.literal_eval(payload_obj)
            except Exception as e2:
                self._log(f"[ToolCall Parser] ast.literal_eval failed: {e2}")

        # Attempt 3: regex salvage for broken command quotes
        if obj is None:
            try:
                if "execute_cktclaw_command" in payload_obj:
                    cmd_match = re.search(r'"command"\s*:\s*"(.+)"', payload_obj, flags=re.DOTALL)
                    cmd = ""
                    if cmd_match:
                        cmd = cmd_match.group(1)
                        # Repair unescaped nested double quotes inside command body
                        cmd = re.sub(r'"([^"]*?)"', lambda m: f"'{m.group(1)}'", cmd)
                        cmd = cmd.replace('\\"', '"').strip()
                    if cmd:
                        obj = {
                            "tool_name": "execute_cktclaw_command",
                            "arguments": {"command": cmd},
                        }
            except Exception as e3:
                self._log(f"[ToolCall Parser] regex salvage failed: {e3}")

        if obj is None:
            self._log(f"[ToolCall Parser] Could not parse tool call payload: {payload_obj[:300]}")
            return None

        tool_name = obj.get("tool_name") or obj.get("name")
        args = obj.get("arguments") or obj.get("args") or {}
        # Some models emit wrapped shape: {"type":"tool_call","name":"...","arguments":"{...}"}
        if isinstance(args, str):
            args_s = args.strip()
            if args_s.startswith("{") and args_s.endswith("}"):
                try:
                    args = json.loads(args_s)
                except Exception:
                    try:
                        args = ast.literal_eval(args_s)
                    except Exception:
                        args = {"command": args}
        if not tool_name:
            return None
        if not isinstance(args, dict):
            args = {"command": str(args)}

        # Guard: only trigger for supported tool name
        if str(tool_name) != "execute_cktclaw_command":
            return None

        return {
            "type": "tool_call",
            "tool_call_id": "local_call_1",
            "name": str(tool_name),
            "arguments": args,
        }

    def _chat_with_local_model_ctx(self, messages: List[Dict[str, str]]) -> str:
        """使用本地 CodeV 模型进行多轮对话（接受预组装 messages + Chat Template + Output Slicing）"""

        # 确保本地模型已加载
        if not self._ensure_local_codev():
            return (
                "⚠️ Failed to load Local CodeV model. "
                "Please try again or switch to DeepSeek-V3 engine."
            )

        try:
            import torch

            # 使用 Chat Template 转换为模型专属 token 序列
            prompt_tensor = self._apply_chat_template_safe(messages)

            input_len = prompt_tensor.shape[1]

            with torch.no_grad():
                outputs = self._chat_codev_model.generate(
                    prompt_tensor,
                    max_new_tokens=2048,
                    do_sample=True,
                    temperature=0.3,
                    top_p=0.9,
                    pad_token_id=self._chat_codev_tokenizer.pad_token_id
                        or self._chat_codev_tokenizer.eos_token_id,
                )

            # 截断：只取生成部分（去掉输入 prompt 的 token）
            generated_tokens = outputs[0][input_len:]
            reply = self._chat_codev_tokenizer.decode(
                generated_tokens, skip_special_tokens=True
            )

            extracted = self._extract_local_tool_call(reply)
            if extracted:
                return extracted

            return self._clean_markdown(reply.strip())

        except Exception as e:
            if self.verbose:
                import traceback
                traceback.print_exc()
            return f"Local model chat failed: {str(e)}"
