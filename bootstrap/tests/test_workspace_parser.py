"""
Tests for WorkspaceParser (.cktclaw/) and inject_project_behavior.

Run from repo parent (PYTHONPATH must include the parent of the ``cktclaw`` package):
  cd /path/to/pythonproject && PYTHONPATH=. python -m pytest cktclaw/bootstrap/tests/test_workspace_parser.py -v
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

# test file: <pythonproject>/cktclaw/bootstrap/tests/test_workspace_parser.py
# parents[3] → pythonproject (parent of importable package ``cktclaw``)
_PYTHONPROJECT = Path(__file__).resolve().parents[3]
if str(_PYTHONPROJECT) not in sys.path:
    sys.path.insert(0, str(_PYTHONPROJECT))

from cktclaw.bootstrap.workspace_parser import (  # noqa: E402
    ProjectBehavior,
    WorkspaceParser,
    inject_project_behavior,
)
from cktclaw.harness.skills.skill_registry import unregister_skill  # noqa: E402


def test_parse_frontmatter_no_fm() -> None:
    text = "# Title\n\nBody only."
    fm, body = WorkspaceParser._parse_frontmatter(text)
    assert fm == {}
    assert "Body only" in body


def test_parse_frontmatter_with_delimiters() -> None:
    text = """---
name: demo
description: A demo skill
---
# Skill body

Hello.
"""
    fm, body = WorkspaceParser._parse_frontmatter(text)
    assert fm.get("name") == "demo"
    assert fm.get("description") == "A demo skill"
    assert "Skill body" in body
    assert "Hello." in body


def test_project_behavior_has_content() -> None:
    empty = ProjectBehavior()
    assert empty.has_content is False

    full = ProjectBehavior(constitution="x", skills=[{"name": "a"}], agents=[])
    assert full.has_content is True


def test_load_project_behavior_no_cktclaw(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.chdir(tmp_path)
        p = WorkspaceParser(verbose=False)
        behavior = await p.load_project_behavior(str(tmp_path))
        assert behavior.constitution is None
        assert behavior.skills == []
        assert behavior.agents == []
        assert behavior.has_content is False

    asyncio.run(_run())


def test_load_constitution_skills_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.chdir(tmp_path)
        ckt = tmp_path / ".cktclaw"
        ckt.mkdir()
        (ckt / "CKTCLAW.md").write_text(
            "# Constitution\n\nProject rules.", encoding="utf-8"
        )

        skill_dir = ckt / "skills" / "timing_check"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            """---
name: timing_check
description: STA hints
skill_type: prompt
user_invocable: true
---
Use this for timing.
""",
            encoding="utf-8",
        )

        agents = ckt / "agents"
        agents.mkdir()
        (agents / "expert.md").write_text(
            """---
name: sta_expert
role: timing
description: Expert agent
---
You are an STA specialist.
""",
            encoding="utf-8",
        )

        p = WorkspaceParser(verbose=False)
        behavior = await p.load_project_behavior(str(tmp_path))

        assert behavior.constitution is not None
        assert "Constitution" in behavior.constitution
        assert len(behavior.skills) == 1
        assert behavior.skills[0]["name"] == "timing_check"
        assert "timing" in behavior.skills[0]["markdown_content"].lower()
        assert len(behavior.agents) == 1
        assert behavior.agents[0]["name"] == "sta_expert"
        assert "STA specialist" in behavior.agents[0]["system_prompt"]
        assert behavior.has_content is True

    asyncio.run(_run())


def test_skill_child_overrides_parent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Same skill name in parent and child .cktclaw: child (cwd) wins."""
    (tmp_path / ".git").mkdir()
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)

    for base in (tmp_path, child):
        sdir = base / ".cktclaw" / "skills" / "dup_skill"
        sdir.mkdir(parents=True)
        tag = "PARENT" if base == tmp_path else "CHILD"
        (sdir / "SKILL.md").write_text(
            f"""---
name: dup_skill
description: from {tag}
---
body {tag}
""",
            encoding="utf-8",
        )

    async def _run() -> None:
        monkeypatch.chdir(child)
        p = WorkspaceParser(verbose=False)
        behavior = await p.load_project_behavior(str(child))
        assert len(behavior.skills) == 1
        assert behavior.skills[0]["description"] == "from CHILD"
        assert "CHILD" in behavior.skills[0]["markdown_content"]

    asyncio.run(_run())


class _FakeStorage:
    def __init__(self) -> None:
        self.messages: List[Dict[str, Any]] = []

    async def add_message(self, **kwargs: Any) -> None:
        self.messages.append(kwargs)


class _FakeCLIState:
    def __init__(self) -> None:
        self.storage = _FakeStorage()
        self.session_id = "test-session-ws"


def test_inject_project_behavior_constitution_and_skill() -> None:
    async def _run() -> None:
        behavior = ProjectBehavior(
            constitution="# Rules\n\nBe concise.",
            constitution_path="/tmp/CKTCLAW.md",
            skills=[
                {
                    "name": "bootstrap_test_skill_xyz",
                    "description": "injected from test",
                    "when_to_use": "testing",
                    "skill_type": "prompt",
                    "user_invocable": True,
                    "paths": None,
                    "markdown_content": "Skill body",
                    "source_path": "/tmp/SKILL.md",
                }
            ],
            agents=[
                {
                    "name": "bootstrap_test_agent",
                    "role": "tester",
                    "description": "d",
                    "system_prompt": "prompt",
                    "source_path": "/tmp/a.md",
                }
            ],
            project_root=".",
        )

        cli = _FakeCLIState()
        try:
            await inject_project_behavior(behavior, cli)

            assert len(cli.storage.messages) == 1
            assert "[Project Constitution" in cli.storage.messages[0]["content"]
            assert "Be concise" in cli.storage.messages[0]["content"]

            from cktclaw.harness.skills.skill_registry import get_skill_registry

            reg = get_skill_registry()
            loaded = await reg.get_skill("bootstrap_test_skill_xyz")
            assert loaded.description == "injected from test"
            assert loaded.markdown_content == "Skill body"
        finally:
            try:
                await unregister_skill("bootstrap_test_skill_xyz")
            except Exception:
                pass

    asyncio.run(_run())


def test_load_project_behavior_cwd_smoke() -> None:
    """Smoke: default cwd load returns a ProjectBehavior."""
    async def _run() -> None:
        p = WorkspaceParser(verbose=False)
        b = await p.load_project_behavior()
        assert isinstance(b, ProjectBehavior)

    asyncio.run(_run())
