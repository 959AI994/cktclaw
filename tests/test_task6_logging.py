"""AST-based tests confirming no /tmp/ writes remain in skill exception handlers."""
import ast
import pathlib

SKILLS_ROOT = pathlib.Path(__file__).parent.parent / "skills"


def _get_tmp_write_sites(filepath):
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    sites = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Name) and func.id == "open"):
            continue
        if node.args:
            first_arg = node.args[0]
            if isinstance(first_arg, ast.Constant) and "/tmp/" in str(first_arg.value):
                sites.append((node.lineno, first_arg.value))
    return sites


def test_rtl_claw_skill_no_tmp_writes():
    sites = _get_tmp_write_sites(SKILLS_ROOT / "rtl_claw_skill.py")
    assert sites == [], f"Found /tmp/ writes: {sites}"


def test_chip_design_skills_no_tmp_writes():
    sites = _get_tmp_write_sites(SKILLS_ROOT / "chip_design_skills.py")
    assert sites == [], f"Found /tmp/ writes: {sites}"
