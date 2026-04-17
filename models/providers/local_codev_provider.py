"""
LocalCodeVProvider - Local GPU-based CodeV model provider.

Handles PyTorch model lazy-loading, GPU memory scanning, auto-selection,
chat template application, and text generation. Preserves the full
multi-strategy tool call parsing for weak local models.
"""

import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Union

from .base import BaseLLMProvider
from ...utils.tool_call_parser import ToolCallParser
from ...utils.verilog_parser import VerilogMetricsExtractor


class LocalCodeVProvider(BaseLLMProvider):
    """Local CodeV model provider with lazy loading and GPU management."""

    # 形如 org/model 的 HuggingFace Hub id（单段斜杠），不按本地路径做存在性检查
    _HF_REPO_ID = re.compile(r"^[\w.-]+/[\w.-]+$")

    def __init__(
        self,
        codev_path: str = "models/llm_decoder/CodeV",
        gpu_id: int = -2,
        verbose: bool = False,
    ):
        self.codev_path = codev_path
        self.requested_gpu_id = gpu_id
        self.gpu_id = gpu_id
        self.device = f"cuda:{gpu_id}" if gpu_id >= 0 else "cpu"
        self.verbose = verbose

        self._model = None
        self._tokenizer = None
        self._loaded = False
        self._load_failure_reason: Optional[str] = None
        self._tool_parser = ToolCallParser(verbose=verbose)
        self._min_free_gpu_gb = float(os.environ.get("CKTCLAW_CODEV_MIN_GB", "2"))

        # Compute physical GPU number
        cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "not set")
        self._physical_gpu = "N/A"
        if cuda_visible != "not set" and gpu_id >= 0:
            visible_list = cuda_visible.split(",")
            if gpu_id < len(visible_list):
                self._physical_gpu = visible_list[gpu_id].strip()

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _notify_user(self, msg: str) -> None:
        """关键错误始终打到 stderr，避免 verbose=False 时用户只看到泛化提示。"""
        print(msg, file=sys.stderr, flush=True)

    @classmethod
    def _expects_local_directory(cls, path: str) -> bool:
        """若返回 True，则 path 应按磁盘目录解析（不存在则立即失败，不空等 Hub）。"""
        p = path.strip()
        if not p or p.startswith(("http://", "https://")):
            return False
        norm = p.replace("\\", "/").lstrip("/")
        # Windows盘符
        if len(p) > 1 and p[1] == ":":
            return True
        if cls._HF_REPO_ID.fullmatch(norm):
            return False
        return True

    # ── GPU Management ──

    def _find_best_gpu(self) -> int:
        """Auto-select GPU with most free memory (≥2GB required)."""
        try:
            import torch
            if not torch.cuda.is_available():
                msg = "  [GPU Selection] CUDA not available, cannot use local model"
                self._log(msg)
                self._notify_user(
                    f"[CktClaw] {msg}\n"
                    "  若使用 Conda：先 `conda activate aig_verilog`（或你的 CUDA 版 PyTorch 环境），"
                    "并确认 `python -c \"import torch; print(torch.cuda.is_available())\"` 为 True。\n"
                    "  若本机只有一块 GPU，启动前可设: export CUDA_VISIBLE_DEVICES=0\n"
                    "  若 nvidia-smi 某卡为 ERR，请从 CUDA_VISIBLE_DEVICES 中排除该物理编号。\n"
                    "  实验室隔离可见卡: export CKTCLAW_CUDA_VISIBLE_DEVICES=2,3,4,5"
                )
                return -1

            gpu_count = torch.cuda.device_count()
            max_free_mem = 0
            best_gpu = -1

            self._log(f"  [GPU Selection] Scanning {gpu_count} visible GPUs...")

            for i in range(gpu_count):
                try:
                    free_mem = torch.cuda.mem_get_info(i)[0] / (1024**3)
                    total_mem = torch.cuda.mem_get_info(i)[1] / (1024**3)

                    cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "")
                    physical_id = "?"
                    if cuda_visible:
                        visible_list = cuda_visible.split(",")
                        if i < len(visible_list):
                            physical_id = visible_list[i].strip()

                    self._log(
                        f"    Logical GPU {i} (Physical {physical_id}): "
                        f"{free_mem:.2f} GB free / {total_mem:.2f} GB total"
                    )

                    if free_mem > max_free_mem and free_mem >= self._min_free_gpu_gb:
                        max_free_mem = free_mem
                        best_gpu = i
                except Exception as e:
                    self._log(f"    Logical GPU {i}: Error checking memory - {e}")
                    continue

            if best_gpu >= 0:
                self._log(f"  [GPU Selection] ✓ Selected Logical GPU {best_gpu} with {max_free_mem:.2f} GB free")
                return best_gpu
            else:
                self._log(
                    f"  [GPU Selection] ✗ No GPU with sufficient memory "
                    f"(≥{self._min_free_gpu_gb}GB free)"
                )
                self._log("  [GPU Selection] → Recommend using DeepSeek API instead")
                self._notify_user(
                    f"[CktClaw] 无满足条件的 GPU：需要 CUDA 且至少一张可见卡剩余显存 ≥ "
                    f"{self._min_free_gpu_gb}GB（可设置 CKTCLAW_CODEV_MIN_GB 调低）。\n"
                    "  环境：请在含 CUDA 版 PyTorch 的 Conda 中运行（如 `conda activate aig_verilog`）。\n"
                    "  检查: echo \"$CUDA_VISIBLE_DEVICES\"（空表示全部物理 GPU 可见）。\n"
                    "  排除占满/故障卡示例: export CUDA_VISIBLE_DEVICES=0,1,2,3\n"
                    "  或固定逻辑卡: export CKTCLAW_CODEV_CHAT_GPU=0"
                )
                return -1

        except Exception as e:
            self._log(f"  [GPU Selection] Error: {e}")
            return -1

    # ── Lazy Loading ──

    def _ensure_loaded(self) -> bool:
        """Lazy-load the local CodeV model (singleton). Returns True on success."""
        if self._loaded:
            return True

        self._load_failure_reason = None

        # 本地目录须存在，避免 transformers 把路径当 Hub id 空等数十秒
        if self._expects_local_directory(self.codev_path):
            abs_path = os.path.abspath(os.path.expanduser(self.codev_path))
            if not os.path.isdir(abs_path):
                self._load_failure_reason = (
                    f"本地模型目录不存在:\n  {abs_path}\n\n"
                    "CktClaw 对话用的 CodeV 权重需要自行准备并放到该路径，或设置:\n"
                    "  export CKTCLAW_CODEV_PATH=/绝对路径/到你的/CodeV或兼容HF快照目录\n\n"
                    "目录内通常需包含 config.json、tokenizer 与模型权重。"
                )
                self._notify_user(f"[CktClaw]\n{self._load_failure_reason}")
                return False

        # Auto GPU selection
        if self.requested_gpu_id == -2:
            self._log(f"\n{'='*70}")
            self._log("  Auto-selecting GPU for Local CodeV...")
            self._log(f"{'='*70}")

            self.gpu_id = self._find_best_gpu()

            if self.gpu_id < 0:
                self._load_failure_reason = (
                    "未选中可用 GPU（需要 CUDA 且满足显存门槛）。可尝试:\n"
                    "  • conda activate aig_verilog（或你的 CUDA PyTorch 环境）\n"
                    "  • export CUDA_VISIBLE_DEVICES=0（若当前可见卡不对）\n"
                    "  • export CKTCLAW_CODEV_CHAT_GPU=0 或 export CKTCLAW_CODEV_MIN_GB=1"
                )
                self._log("  ✗ No suitable GPU found for Local CodeV")
                self._log("  → Please use DeepSeek API engine instead")
                self._log(f"{'='*70}\n")
                self._notify_user(f"[CktClaw] {self._load_failure_reason}")
                return False

            self.device = f"cuda:{self.gpu_id}"

            cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "not set")
            if cuda_visible != "not set":
                visible_list = cuda_visible.split(",")
                if self.gpu_id < len(visible_list):
                    self._physical_gpu = visible_list[self.gpu_id].strip()

        self._log(f"\n{'='*70}")
        self._log("  Loading Local CodeV for Chat/Analysis (Lazy Loading)")
        self._log(f"  Path: {self.codev_path}")
        self._log(f"  Target: Logical GPU {self.gpu_id} → Physical GPU {self._physical_gpu}")
        self._log("  ⚠️  This model is INDEPENDENT from the LogicRT inference CodeV")
        self._log(f"{'='*70}")

        _old_tqdm_disable = os.environ.get("TQDM_DISABLE")
        if not self.verbose:
            os.environ["TQDM_DISABLE"] = "1"

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            import warnings

            t0 = time.time()

            self._tokenizer = AutoTokenizer.from_pretrained(
                self.codev_path, trust_remote_code=True
            )

            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*torch_dtype.*deprecated.*")
                warnings.filterwarnings("ignore", message=".*rotary_emb.*")
                warnings.filterwarnings("ignore", message=".*newly initialized.*")

                self._model = AutoModelForCausalLM.from_pretrained(
                    self.codev_path,
                    dtype=torch.float16,
                    device_map={"": self.gpu_id},
                    trust_remote_code=True,
                )
            self._model.eval()

            elapsed = time.time() - t0
            self._loaded = True

            has_chat_template = (
                hasattr(self._tokenizer, 'chat_template')
                and self._tokenizer.chat_template is not None
            )
            actual_device = next(self._model.parameters()).device

            self._log(f"\n  ✓ Local CodeV loaded successfully, took {elapsed:.1f}s")
            self._log(f"  ✓ Device: Logical GPU {self.gpu_id} (Physical GPU {self._physical_gpu}) → {actual_device}")
            self._log(f"  ✓ dtype=float16, device_map={{\"\":{self.gpu_id}}}")
            self._log(f"  ✓ chat_template: {'available (native)' if has_chat_template else 'NOT found (will use fallback ChatML)'}")
            self._log(f"  ✓ eos_token: {self._tokenizer.eos_token!r} (id={self._tokenizer.eos_token_id})")
            self._log(f"  ✓ pad_token: {self._tokenizer.pad_token!r} (id={self._tokenizer.pad_token_id})")
            self._log(f"{'='*70}\n")
            self._load_failure_reason = None
            return True

        except Exception as e:
            import torch as _torch
            if isinstance(e, _torch.cuda.OutOfMemoryError):
                self._load_failure_reason = (
                    f"GPU 显存不足 (OOM)，逻辑 GPU {self.gpu_id}。"
                    "可换卡、释放显存或使用 /model 切换 DeepSeek。"
                )
                self._log(f"\n  ✗ GPU Out of Memory!")
                self._log(f"  → Logical GPU {self.gpu_id} (Physical GPU {self._physical_gpu}) does not have enough memory")
                self._log("  → Please switch to DeepSeek API engine (/model or /engine deepseek)")
                self._notify_user(f"[CktClaw] {self._load_failure_reason}")
            else:
                self._load_failure_reason = f"{type(e).__name__}: {e}"
                self._log(f"  ✗ Failed to load Local CodeV: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
                self._log("  → User will see an error message in chat")
                self._notify_user(
                    f"[CktClaw] 加载本地模型失败: {self._load_failure_reason}"
                )
            self._log(f"{'='*70}\n")
            self._loaded = False
            return False
        finally:
            if _old_tqdm_disable is not None:
                os.environ["TQDM_DISABLE"] = _old_tqdm_disable
            else:
                os.environ.pop("TQDM_DISABLE", None)

    # ── Chat Template ──

    def _apply_chat_template_safe(self, messages: List[Dict[str, str]]):
        """Convert structured messages to model-specific token tensors."""
        import torch

        tokenizer = self._tokenizer
        model = self._model

        has_chat_template = (
            hasattr(tokenizer, 'chat_template')
            and tokenizer.chat_template is not None
        )

        if has_chat_template:
            try:
                result = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                )
                # transformers ≥5.x may return BatchEncoding instead of a raw tensor
                if hasattr(result, 'input_ids'):
                    prompt_tensor = result.input_ids.to(model.device)
                else:
                    prompt_tensor = result.to(model.device)
                return prompt_tensor
            except Exception as e:
                self._log(f"  [ChatTemplate] apply_chat_template failed: {e}, falling back to manual ChatML")

        # Fallback: manual ChatML format
        chatml_text = ""
        for msg in messages:
            chatml_text += f"<|im_start|>{msg['role']}\n{msg['content']}<|im_end|>\n"
        chatml_text += "<|im_start|>assistant\n"

        prompt_tensor = tokenizer(
            chatml_text,
            return_tensors="pt",
            truncation=True,
            max_length=16384,
        ).input_ids.to(model.device)

        return prompt_tensor

    @staticmethod
    def _clean_markdown(text: str) -> str:
        text = re.sub(r'\n{3,}', '\n\n', text)
        lines = [line.rstrip() for line in text.split('\n')]
        return '\n'.join(lines).strip()

    # ── Interface Methods ──

    def chat_with_context(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict]] = None,
    ) -> Union[str, Dict[str, Any]]:
        """Multi-turn chat using local CodeV model."""
        if not self._ensure_loaded():
            detail = self._load_failure_reason or "原因未知"
            return (
                "⚠️ 无法加载本地 CodeV 模型。\n\n"
                f"{detail}\n\n"
                "也可输入 /model 切换到 DeepSeek 云端引擎。"
            )

        try:
            import torch

            prompt_tensor = self._apply_chat_template_safe(messages)
            input_len = prompt_tensor.shape[1]

            with torch.no_grad():
                outputs = self._model.generate(
                    prompt_tensor,
                    max_new_tokens=2048,
                    do_sample=True,
                    temperature=0.3,
                    top_p=0.9,
                    pad_token_id=self._tokenizer.pad_token_id
                        or self._tokenizer.eos_token_id,
                )

            generated_tokens = outputs[0][input_len:]
            reply = self._tokenizer.decode(
                generated_tokens, skip_special_tokens=True
            )

            extracted = self._tool_parser.parse(reply)
            if extracted:
                return extracted

            return self._clean_markdown(reply.strip())

        except Exception as e:
            if self.verbose:
                import traceback
                traceback.print_exc()
            return f"Local model chat failed: {str(e)}"

    def analyze(
        self,
        verilog_code: str,
        metrics: Dict[str, Any],
        system_prompt: str = "",
    ) -> str:
        """Analyze Verilog code using local CodeV model."""
        if not self._ensure_loaded():
            detail = self._load_failure_reason or "原因未知"
            return (
                "⚠️ 无法加载本地 CodeV 模型。\n\n"
                f"{detail}\n\n"
                + VerilogMetricsExtractor.generate_fallback_analysis(verilog_code, metrics)
            )

        try:
            import torch

            msg_list: List[Dict[str, str]] = []
            if system_prompt:
                msg_list.append({"role": "system", "content": system_prompt})
            msg_list.append({
                "role": "user",
                "content": VerilogMetricsExtractor.build_analysis_prompt(verilog_code, metrics),
            })

            prompt_tensor = self._apply_chat_template_safe(msg_list)
            input_len = prompt_tensor.shape[1]

            with torch.no_grad():
                outputs = self._model.generate(
                    prompt_tensor,
                    max_new_tokens=2048,
                    do_sample=True,
                    temperature=0.3,
                    top_p=0.9,
                    pad_token_id=self._tokenizer.pad_token_id
                        or self._tokenizer.eos_token_id,
                )

            generated_tokens = outputs[0][input_len:]
            analysis = self._tokenizer.decode(
                generated_tokens, skip_special_tokens=True
            )

            return analysis.strip()

        except Exception as e:
            if self.verbose:
                import traceback
                traceback.print_exc()
            return f"Local model analysis failed: {str(e)}"

    def summarize_after_tool(
        self,
        messages: List[Dict[str, str]],
        tool_call_id: str,
        tool_name: str,
        tool_args: Dict[str, Any],
        tool_output: str,
    ) -> str:
        """For local model, return a simple summary of tool output."""
        return f"工具已执行完成，结果如下：\n\n{tool_output}"
