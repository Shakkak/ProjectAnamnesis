"""
Vault Validator (4.1) — deterministic checks on vault/*.md files.

Exit codes:
  0 — all pass (warnings allowed)
  1 — one or more failures

Usage:
  python3 tools/vault_validator.py
  python3 tools/vault_validator.py vault/backpropagation.md vault/loss-mse.md
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent
_EXCLUDED_TAGS_FILE = _ROOT / "tools" / "excluded_tags.json"
_MAX_LINES = 300
_REQUIRED_FRONTMATTER = {"title", "tags", "status"}

# Load all excluded tags into a flat set
_excluded = json.loads(_EXCLUDED_TAGS_FILE.read_text())
_EXCLUDED_TAG_SET = {t for cat in _excluded.values() for t in cat}


def _parse_frontmatter(text: str) -> tuple[dict | None, str]:
    """Return (frontmatter_dict, body) or (None, full_text) if no frontmatter."""
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    fm_text = text[3:end].strip()
    body = text[end + 4:].lstrip("\n")
    fm: dict = {}
    for line in fm_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            fm[k.strip()] = v.strip()
    return fm, body


def _parse_tags(fm: dict) -> list[str]:
    """Extract tags list from frontmatter dict (handles '[a, b, c]' format)."""
    raw = fm.get("tags", "")
    raw = raw.strip("[]")
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_related(fm: dict) -> list[str]:
    """Extract related slugs from frontmatter dict."""
    raw = fm.get("related", "")
    raw = raw.strip("[]")
    return [r.strip() for r in raw.split(",") if r.strip()]


def _wikilinks(body: str) -> list[str]:
    """Return all [[slug]] targets found in body."""
    return re.findall(r"\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]", body)


def validate_file(path: Path, all_slugs: set[str]) -> list[tuple[str, str]]:
    """
    Validate one vault file. Returns list of (level, message) where
    level is 'FAIL' or 'WARN'.
    """
    issues: list[tuple[str, str]] = []
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()

    # 1. Kebab-case filename
    if not re.fullmatch(r"[a-z0-9][a-z0-9\-]*\.md", path.name):
        issues.append(("FAIL", f"filename not kebab-case: {path.name}"))

    # 2. Frontmatter present
    fm, body = _parse_frontmatter(text)
    if fm is None:
        issues.append(("FAIL", "no YAML frontmatter block"))
        return issues  # can't proceed without frontmatter

    # 3. Required fields
    for field in _REQUIRED_FRONTMATTER:
        if not fm.get(field, "").strip():
            issues.append(("FAIL", f"frontmatter missing required field: '{field}'"))

    # 4. Tags not exclusively umbrella/excluded
    tags = _parse_tags(fm)
    if not tags:
        issues.append(("WARN", "no tags"))
    else:
        non_excluded = [t for t in tags if t not in _EXCLUDED_TAG_SET]
        if not non_excluded:
            issues.append(("FAIL", "all tags are umbrella/excluded — add at least one specific concept tag"))

    # 5. related entries resolve
    for slug in _parse_related(fm):
        if slug not in all_slugs:
            issues.append(("WARN", f"related '{slug}' does not match any vault file"))

    # 6. Wikilinks resolve
    for link in _wikilinks(body):
        if link not in all_slugs:
            issues.append(("WARN", f"wikilink [[{link}]] does not match any vault file"))

    # 7. File size
    if len(lines) > _MAX_LINES:
        issues.append(("WARN", f"{len(lines)} lines — may cover multiple concepts (threshold {_MAX_LINES})"))

    return issues


def main(paths: list[Path] | None = None, vault: Path | None = None) -> int:
    if vault is None:
        vault = _ROOT / "content" / "vault"
    if paths is None:
        paths = sorted(p for p in vault.rglob("*.md") if p.name != "TODO.md")

    all_slugs = {p.stem for p in vault.rglob("*.md")}

    total_files = len(paths)
    fail_count = 0
    warn_count = 0
    files_with_issues = 0

    for path in paths:
        issues = validate_file(path, all_slugs)
        fails = [m for lvl, m in issues if lvl == "FAIL"]
        warns = [m for lvl, m in issues if lvl == "WARN"]
        fail_count += len(fails)
        warn_count += len(warns)
        if issues:
            files_with_issues += 1
            print(f"\n{path.name}")
            for msg in fails:
                print(f"  FAIL  {msg}")
            for msg in warns:
                print(f"  WARN  {msg}")

    print(f"\n── Summary {'─'*40}")
    print(f"   files checked : {total_files}")
    print(f"   files with issues: {files_with_issues}")
    print(f"   failures : {fail_count}")
    print(f"   warnings : {warn_count}")
    if fail_count == 0:
        print("   result   : PASS")
    else:
        print("   result   : FAIL")
    return 1 if fail_count else 0


if __name__ == "__main__":
    _parser = argparse.ArgumentParser(description="Vault validator")
    _parser.add_argument("--bank", metavar="PATH",
                         default=os.environ.get("BANK_PATH"),
                         help="External data root (default: content/ in this repo)")
    _parser.add_argument("files", nargs="*", help="Specific vault .md files to check")
    _args = _parser.parse_args()

    _bank  = Path(_args.bank).resolve() if _args.bank else _ROOT / "content"
    _VAULT = _bank / "vault"  # noqa: N816

    target_paths = [Path(f) for f in _args.files] if _args.files else None
    sys.exit(main(target_paths, vault=_VAULT))
