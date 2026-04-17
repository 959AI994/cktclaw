#!/usr/bin/env python3
"""
下载 Qwen/Qwen2.5-3B 模型到本地目录。
用法: conda run -n logic python download_qwen.py
"""

import os
import sys

def download_qwen():
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print("❌ huggingface_hub 未安装，请运行: pip install huggingface_hub")
        sys.exit(1)

    repo_id = "Qwen/Qwen2.5-3B-Instruct"
    local_dir = os.path.join(os.path.dirname(__file__), "models", "qwen", "Qwen2.5-3B-Instruct")
    os.makedirs(local_dir, exist_ok=True)

    print(f"📥 开始下载 {repo_id}（Instruct 对话版）")
    print(f"📁 保存路径: {local_dir}")
    print("⏳ 下载中（模型约 6GB，请耐心等待）...\n")

    # 使用国内镜像加速（如需要）
    hf_endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
    print(f"🌐 HuggingFace endpoint: {hf_endpoint}")

    try:
        path = snapshot_download(
            repo_id=repo_id,
            local_dir=local_dir,
            # 排除旧格式 .bin 权重，只保留 .safetensors
            ignore_patterns=["*.bin", "original/*", "*.msgpack"],
        )
        print(f"\n✅ 下载完成！模型保存在: {path}")
        print("\n使用方法:")
        print(f"  export CKTCLAW_QWEN_PATH={local_dir}")
        print("  python main.py")
        return path
    except KeyboardInterrupt:
        print("\n⚠️ 下载已中断，可重新运行脚本继续下载（支持断点续传）")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ 下载失败: {e}")
        print("\n提示：如果网络较慢，可以设置国内镜像：")
        print("  export HF_ENDPOINT=https://hf-mirror.com")
        print("  python download_qwen.py")
        sys.exit(1)


if __name__ == "__main__":
    download_qwen()
