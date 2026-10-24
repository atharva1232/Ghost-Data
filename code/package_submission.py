"""Package code only; never includes the organizer dataset, outputs, or secrets."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def package():
    code = Path(__file__).resolve().parent
    target = code.parent / "dist" / "code.zip"
    target.parent.mkdir(exist_ok=True)
    with ZipFile(target, "w", ZIP_DEFLATED) as archive:
        for path in sorted(code.rglob("*")):
            rel = path.relative_to(code)
            if not path.is_file() or any(part.startswith(".") or part in (
                    "__pycache__", "node_modules", "artifacts", "dataset", "data", "dist", "build") for part in rel.parts):
                continue
            if path.suffix not in (".py", ".md", ".toml", ".txt", ".json", ".html", ".js", ".css", ".svg") or "examples" in rel.parts:
                continue
            archive.write(path, Path("code") / rel)
    print(target)


if __name__ == "__main__":
    package()
