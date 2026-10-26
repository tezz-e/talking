#!/usr/bin/env python3
"""
Generates a clean, consolidated codebase_dump.txt for Gemini / LLM full-repo audits.
Excludes venv, .git, caches, vector DBs, browser session caches, and secrets.
"""

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
OUTPUT_FILE = ROOT_DIR / "codebase_dump.txt"

# Directories to strictly exclude
EXCLUDE_DIRS = {
    ".git",
    "venv",
    "__pycache__",
    ".agents",
    ".gemini",
    "node_modules",
    "data/db",
    "data/ig_session",
    "data/exports",
}

# Specific files to exclude
EXCLUDE_FILES = {
    ".env",
    "codebase_dump.txt",
    "traceback.txt",
    "progress.txt",
}

# Allowed file extensions
ALLOWED_EXTENSIONS = {
    ".py",
    ".js",
    ".html",
    ".css",
    ".md",
    ".json",
    ".bat",
    ".example",
}

def is_excluded(path: Path) -> bool:
    rel_path = path.relative_to(ROOT_DIR).as_posix()
    if path.name in EXCLUDE_FILES:
        return True
    for exc in EXCLUDE_DIRS:
        if rel_path == exc or rel_path.startswith(exc + "/"):
            return True
    return False

def main():
    collected_files = []
    for root, dirs, files in os.walk(ROOT_DIR):
        root_path = Path(root)
        if is_excluded(root_path):
            dirs.clear()  # Don't recurse into excluded directories
            continue
        
        # Filter dirs in-place to avoid descending into excluded ones
        dirs[:] = [d for d in dirs if not is_excluded(root_path / d)]

        for file_name in files:
            file_path = root_path / file_name
            if is_excluded(file_path):
                continue
            if file_path.suffix in ALLOWED_EXTENSIONS or file_name in {".env.example", "requirements.txt"}:
                collected_files.append(file_path)

    # Sort files cleanly by relative path
    collected_files.sort(key=lambda p: p.relative_to(ROOT_DIR).as_posix())

    total_lines = 0
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        out.write("=" * 80 + "\n")
        out.write("TALKING (tezz-e/talking) - COMPLETE REPOSITORY CODEBASE DUMP\n")
        out.write(f"Total Files: {len(collected_files)}\n")
        out.write("=" * 80 + "\n\n")

        for fpath in collected_files:
            rel = fpath.relative_to(ROOT_DIR).as_posix()
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
            except Exception as e:
                content = f"[Error reading file: {e}]"

            lines = content.splitlines()
            total_lines += len(lines)

            out.write("=" * 80 + "\n")
            out.write(f"FILE: {rel} ({len(lines)} lines)\n")
            out.write("=" * 80 + "\n")
            out.write(content)
            if not content.endswith("\n"):
                out.write("\n")
            out.write("\n\n")

    size_kb = OUTPUT_FILE.stat().st_size / 1024
    print(f"Successfully generated {OUTPUT_FILE.name}")
    print(f"  Files bundled: {len(collected_files)}")
    print(f"  Total lines:   {total_lines}")
    print(f"  File size:     {size_kb:.1f} KB")

if __name__ == "__main__":
    main()
