"""
LocalCodeVProvider - Local GPU-based CodeV model provider.

Handles PyTorch model lazy-loading, GPU memory scanning, auto-selection,
chat template application, and text generation. Preserves the full
multi-strategy tool call parsing for weak local models.
"""

import os
import re
import time
from typing import Any, Dict, List, Optional, Union

from .base import BaseLLMProvider
from ...utils.tool_call_parser import ToolCallParser
from ...utils.verilog_parser import VerilogMetricsExtractor


class LocalCodeVProvider(BaseLLMProvider):
    """Local CodeV model provider with lazy loading and GPU management."""

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
        self._tool_parser = ToolCallParser(verbose=verbose)

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

    # ── GPU Management ──

    def _find_best_gpu(self) -> int:
        """Auto-select GPU with most free memory (≥2GB required)."""
        try:
            import torch
            if not torch.cuda.is_available():
                self._log("  [GPU Selection] CUDA not available, cannot use local model")
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
                self._log("  [GPU Selection] ✗ No GPU with sufficient memory (≥2GB free)")
                self._log("  [GPU Selection] → Recommend using DeepSeek API instead")
                return -1

        except Exception as e:
            self._log(f"  [GPU Selection] Error: {e}")
            return -1

    # ── Lazy Loading ──

    def _ensure_loaded(self) -> bool:
        """Lazy-load the local CodeV model (singleton). Returns True on success."""
        if self._loaded:
            return True

        # Auto GPU selection
        if self.requested_gpu_id == -2:
            self._log(f"\n{'='*70}")
            self._log("  Auto-selecting GPU for Local CodeV...")
            self._log(f"{'='*70}")

            self.gpu_id = self._find_best_gpu()

            if self.gpu_id < 0:
                self._log("  ✗ No suitable GPU found for Local CodeV")
                self._log("  → Please use DeepSeek API engine instead")
                self._log(f"{'='*70}\n")
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
            return True

        except Exception as e:
            import torch as _torch
            if isinstance(e, _torch.cuda.OutOfMemoryError):
                self._log(f"\n  ✗ GPU Out of Memory!")
                self._log(f"  → Logical GPU {self.gpu_id} (Physical GPU {self._physical_gpu}) does not have enough memory")
                self._log("  → Please switch to DeepSeek API engine (/model or /engine deepseek)")
            else:
                self._log(f"  ✗ Failed to load Local CodeV: {e}")
                if self.verbose:
                    import traceback
                    traceback.print_exc()
                self._log("  → User will see an error message in chat")
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
                prompt_tensor = tokenizer.apply_chat_template(
                    messages,
                    tokenize=True,
                    add_generation_prompt=True,
                    return_tensors="pt",
                ).to(model.device)
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
            return (
                "⚠️ Failed to load Local CodeV model. "
                "Please try again or switch to DeepSeek-V3 engine."
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
            return (
                "⚠️ Failed to load Local CodeV model. "
                "Please try again or switch to DeepSeek-V3 engine.\n\n"
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
