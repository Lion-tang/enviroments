import ast
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOTS = (
    BACKEND_ROOT / "app",
    BACKEND_ROOT / "infrastructure",
    BACKEND_ROOT / "tests",
)


def _python_files():
    return sorted(
        path
        for root in SOURCE_ROOTS
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts
    )


def _annotations(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.arg) and node.annotation is not None:
            yield node.annotation
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                yield node.returns
        elif isinstance(node, ast.AnnAssign):
            yield node.annotation


def test_backend_parses_with_python39_grammar():
    for path in _python_files():
        ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
            feature_version=9,
        )


def test_annotations_do_not_use_pep604_union_operator():
    violations = []
    for path in _python_files():
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for annotation in _annotations(tree):
            if any(
                isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
                for node in ast.walk(annotation)
            ):
                violations.append(
                    f"{path.relative_to(BACKEND_ROOT)}:{annotation.lineno}"
                )

    assert violations == [], (
        "Python 3.10+ union annotations found: " + ", ".join(violations)
    )
