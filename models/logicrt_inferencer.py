"""
LogicRT 推理器：单例封装，处理 AIG→Verilog 逆向生成
"""

import sys
import os
import time
from pathlib import Path
from typing import Tuple, Dict, Any, Optional

# 设置项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
os.chdir(PROJECT_ROOT)
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')

import torch

from scripts.inference_single_modal import (
    load_trained_model,
    resolve_prompt_and_instruction,
    sanitize_generated_verilog,
)
from scripts.train_pipeline import fill_instruction_stats


class LogicRTInferencer:
    """
    LogicRT 单例推理器
    首次初始化时加载模型权重，后续快速推理
    """

    _instance: Optional["LogicRTInferencer"] = None
    _loaded_checkpoint: Optional[str] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(
        self,
        checkpoint_dir: str = "output/full_training_norm/dpo_batch_20260319_103708/checkpoint-200",
        codev_path: str = "models/llm_decoder/CodeV",
        aig_encoder_type: str = "mgvga_improved",
        gpu_id: int = 0,
    ):
        # 如果已加载相同 checkpoint，直接返回
        ckpt_key = str(Path(checkpoint_dir).resolve())
        if self._initialized and self._loaded_checkpoint == ckpt_key:
            return

        print(f"\n{'='*70}")
        print("  LogicRT Inferencer — 初始化模型")
        print(f"{'='*70}")

        if gpu_id >= 0 and torch.cuda.is_available():
            self.device = f"cuda:{gpu_id}"
        else:
            self.device = "cpu"

        # 打印 GPU 隔离信息
        cuda_visible = os.environ.get("CUDA_VISIBLE_DEVICES", "not set")
        physical_gpu = "N/A"
        if cuda_visible != "not set" and self.device.startswith("cuda:"):
            visible_list = cuda_visible.split(",")
            logical_id = int(self.device.split(":")[1])
            if logical_id < len(visible_list):
                physical_gpu = visible_list[logical_id].strip()

        print(f"  Checkpoint : {checkpoint_dir}")
        print(f"  LLM        : {codev_path}")
        print(f"  Device     : {self.device} (physical GPU {physical_gpu})")
        print(f"  CUDA_VISIBLE_DEVICES = {cuda_visible}")

        t0 = time.time()
        self.model, self.aig_encoder = load_trained_model(
            checkpoint_dir=checkpoint_dir,
            device=self.device,
            aig_encoder_type=aig_encoder_type,
            llm_model_path=codev_path,
        )
        self.model.eval()
        self.aig_encoder.eval()

        self.prompt_style, self.instruction = resolve_prompt_and_instruction(
            Path(checkpoint_dir), None, None
        )

        elapsed = time.time() - t0
        print(f"\n  ✓ 模型加载完成，耗时 {elapsed:.1f}s")
        print(f"  ✓ LogicRT loaded on {self.device} (physical GPU {physical_gpu})")
        print(f"  prompt_style={self.prompt_style!r}  instruction len={len(self.instruction)}")
        print(f"{'='*70}\n")

        self._initialized = True
        self._loaded_checkpoint = ckpt_key

    def generate(
        self,
        aig_pt_path: str,
        max_new_tokens: int = 768,
        temperature: float = 0.0,
        top_p: float = 0.9,
    ) -> Tuple[str, Dict[str, Any]]:
        """
        生成 Verilog 代码

        Returns:
            (verilog_code, info_dict)
        """
        aig_pt_path = str(Path(aig_pt_path).resolve())

        # 使用兼容性加载器加载 PyG 数据
        try:
            # 尝试使用 AI4EDA 工具包的兼容性加载器
            import sys
            toolkit_path = Path("/home/wjx/pythonproject/AI4EDA-OpenABC-Data-Toolkit")
            if str(toolkit_path) not in sys.path:
                sys.path.insert(0, str(toolkit_path))

            from ai4eda.utils.version_compat import load_pt_auto
            aig_data_raw = load_pt_auto(aig_pt_path, map_location='cpu')
        except Exception as e:
            # 回退到 torch.load
            aig_data_raw = torch.load(aig_pt_path, map_location='cpu', weights_only=False)

        # 提取数据（兼容旧版 PyG）
        def extract_attr(data, attr, default=None):
            try:
                if hasattr(data, '_store') and hasattr(data._store, '_mapping'):
                    return data._store._mapping.get(attr, default)
            except:
                pass
            try:
                return data.__dict__.get(attr, default)
            except:
                pass
            # 尝试直接访问属性
            try:
                return getattr(data, attr, default)
            except:
                pass
            return default

        node_type = extract_attr(aig_data_raw, 'node_type')
        edge_index = extract_attr(aig_data_raw, 'edge_index')
        longest_path = extract_attr(aig_data_raw, 'longest_path')

        if node_type is None or edge_index is None:
            raise ValueError("无法从 AIG 数据提取 node_type 或 edge_index")

        # 转换为张量
        if not isinstance(node_type, torch.Tensor):
            node_type = torch.tensor(node_type)
        if not isinstance(edge_index, torch.Tensor):
            edge_index = torch.tensor(edge_index)
        if longest_path is None:
            longest_path = torch.tensor(0)
        elif not isinstance(longest_path, torch.Tensor):
            longest_path = torch.tensor(longest_path)

        # 统计特征
        num_pi = int((node_type == 0).sum())
        num_po = int((node_type == 1).sum())
        num_and = int((node_type == 2).sum())
        depth = int(longest_path.item())
        stats = torch.tensor([[num_pi, num_po, num_and, depth]], dtype=torch.float32)

        # 编码 AIG
        d = self.device
        aig_input = {
            'input_nodes': (node_type + 1).unsqueeze(0).to(d),
            'input_edges': edge_index.unsqueeze(0).to(d),
            'padding_mask': torch.ones(1, node_type.shape[0], device=d),
            'stats': stats.to(d),
            'aig_file': aig_pt_path,
        }

        with torch.no_grad():
            aig_emb = self.aig_encoder(aig_input)

        # 填充 instruction
        instr = fill_instruction_stats(self.instruction, stats) \
                if self.prompt_style in ("instruction", "instruction_no_explanation") \
                else self.instruction

        # 生成 Verilog
        do_sample = temperature > 0
        raw = self.model.generate_verilog(
            aig_embedding=aig_emb,
            stats=stats.to(d),
            instruction=instr,
            max_new_tokens=max_new_tokens,
            temperature=temperature if do_sample else 1.0,
            top_p=top_p,
            do_sample=do_sample,
            verbose=False,
            prefix_module=False,
            prompt_style=self.prompt_style,
            raw_unconstrained=True,
        )

        verilog = sanitize_generated_verilog(raw)

        info = {
            "num_pi": num_pi,
            "num_po": num_po,
            "num_and": num_and,
            "logic_depth": depth,
            "aig_emb_shape": list(aig_emb.shape),
            "prompt_style": self.prompt_style,
            "generated_chars": len(verilog),
            "raw_chars": len(raw),
        }

        return verilog, info
