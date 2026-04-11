"""
Custom Skills Auto-Discovery Engine

自动发现并加载 custom_skills/ 目录下的自定义技能
"""

import os
import sys
import importlib.util
import inspect
from pathlib import Path
from typing import List, Optional
import asyncio

from harness import SkillDefinition, register_skill, get_skill_registry
from harness.skills.skill_types import SkillType


class BaseSkill:
    """
    自定义技能基类

    所有自定义技能必须继承此类并实现以下方法：
    - get_skill_definition(): 返回 SkillDefinition
    - execute(args, context): 执行技能逻辑
    """

    def get_skill_definition(self) -> SkillDefinition:
        """返回技能定义"""
        raise NotImplementedError("子类必须实现 get_skill_definition()")

    async def execute(self, args: str, context: dict) -> List[dict]:
        """执行技能"""
        raise NotImplementedError("子类必须实现 execute()")


class CustomSkillLoader:
    """自定义技能加载器"""

    def __init__(self, custom_skills_dir: str):
        self.custom_skills_dir = Path(custom_skills_dir)
        self.loaded_skills: List[SkillDefinition] = []

    def discover_skills(self) -> List[Path]:
        """
        发现所有自定义技能文件

        Returns:
            技能文件路径列表
        """
        if not self.custom_skills_dir.exists():
            print(f"⚠️  自定义技能目录不存在: {self.custom_skills_dir}")
            return []

        skill_files = []
        for file_path in self.custom_skills_dir.glob("*.py"):
            if file_path.name.startswith("_"):
                continue  # 跳过私有文件
            skill_files.append(file_path)

        return skill_files

    def load_skill_from_file(self, file_path: Path) -> Optional[SkillDefinition]:
        """
        从文件加载技能

        Args:
            file_path: 技能文件路径

        Returns:
            SkillDefinition 或 None
        """
        try:
            # 动态导入模块
            module_name = file_path.stem
            spec = importlib.util.spec_from_file_location(module_name, file_path)
            if spec is None or spec.loader is None:
                print(f"❌ 无法加载模块: {file_path}")
                return None

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # 查找 BaseSkill 子类
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if issubclass(obj, BaseSkill) and obj is not BaseSkill:
                    # 实例化技能类
                    skill_instance = obj()
                    skill_def = skill_instance.get_skill_definition()

                    # 包装执行器
                    async def wrapped_executor(args: str, context: dict):
                        return await skill_instance.execute(args, context)

                    # 更新执行器
                    skill_def.executor = wrapped_executor

                    print(f"✓ 发现自定义技能: {skill_def.name} ({file_path.name})")
                    return skill_def

            print(f"⚠️  文件中未找到 BaseSkill 子类: {file_path}")
            return None

        except Exception as e:
            print(f"❌ 加载技能失败 {file_path}: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def load_all_skills(self) -> int:
        """
        加载所有自定义技能

        Returns:
            成功加载的技能数量
        """
        skill_files = self.discover_skills()

        if not skill_files:
            print("ℹ️  未发现自定义技能")
            return 0

        print(f"\n{'='*60}")
        print(f"🔍 发现 {len(skill_files)} 个自定义技能文件")
        print(f"{'='*60}")

        loaded_count = 0
        for file_path in skill_files:
            skill_def = self.load_skill_from_file(file_path)
            if skill_def:
                try:
                    # 注册技能
                    await register_skill(skill_def)
                    self.loaded_skills.append(skill_def)
                    loaded_count += 1
                except Exception as e:
                    print(f"❌ 注册技能失败 {skill_def.name}: {e}")

        print(f"{'='*60}")
        print(f"✓ 成功加载 {loaded_count}/{len(skill_files)} 个自定义技能")
        print(f"{'='*60}\n")

        return loaded_count


async def auto_discover_custom_skills(project_root: str) -> int:
    """
    自动发现并加载自定义技能

    Args:
        project_root: 项目根目录

    Returns:
        成功加载的技能数量
    """
    custom_skills_dir = os.path.join(project_root, "custom_skills")
    loader = CustomSkillLoader(custom_skills_dir)
    return await loader.load_all_skills()


# 示例：创建自定义技能模板
CUSTOM_SKILL_TEMPLATE = '''"""
自定义技能示例

将此文件复制到 custom_skills/ 目录下，修改后即可自动加载
"""

import asyncio
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from cktclaw.skills.custom_skill_loader import BaseSkill
from harness import SkillDefinition, SkillType, LoadedFrom


class MyCustomSkillInput(BaseModel):
    """输入参数定义"""
    param1: str = Field(..., description="参数1")
    param2: int = Field(default=10, description="参数2")


class MyCustomSkill(BaseSkill):
    """我的自定义技能"""

    def get_skill_definition(self) -> SkillDefinition:
        """返回技能定义"""
        return SkillDefinition(
            name="my_custom_skill",
            skill_type=SkillType.TOOL,
            description="这是一个自定义技能示例",
            display_name="My Custom Skill",
            aliases=["custom", "my-skill"],
            executor=None,  # 会被自动设置
            loaded_from=LoadedFrom.USER_SETTINGS,
            version="1.0.0",
            metadata={
                "author": "Your Name",
                "category": "custom",
            }
        )

    async def execute(self, args: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        执行技能逻辑

        Args:
            args: 命令参数
            context: 执行上下文（包含 cli_state 等）

        Returns:
            结果消息列表
        """
        try:
            # 解析输入
            skill_input = MyCustomSkillInput(param1=args, param2=20)

            # 执行你的逻辑
            result = f"处理完成: {skill_input.param1}, {skill_input.param2}"

            # 返回结果
            return [{
                "type": "text",
                "text": f"✅ {result}"
            }]

        except Exception as e:
            return [{
                "type": "text",
                "text": f"❌ 执行失败: {e}"
            }]
'''


def create_custom_skill_template(output_path: str):
    """创建自定义技能模板文件"""
    with open(output_path, 'w') as f:
        f.write(CUSTOM_SKILL_TEMPLATE)
    print(f"✓ 自定义技能模板已创建: {output_path}")


if __name__ == "__main__":
    # 测试加载器
    import sys
    project_root = sys.argv[1] if len(sys.argv) > 1 else "."

    async def test():
        count = await auto_discover_custom_skills(project_root)
        print(f"\n总共加载了 {count} 个自定义技能")

    asyncio.run(test())
