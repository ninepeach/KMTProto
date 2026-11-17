#!/usr/bin/env python3
"""Consistency checks for the KMTProto V1 specification documents.

Checks clause numbering, clause cross-references, relative Markdown links, and that the registries in
spec/protocol.md agree with the golden vectors and with tools/check_vectors.py. It does not execute any
protocol behavior.
"""
import importlib.util
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = ROOT / "spec" / "protocol.md"
GOLDEN = ROOT / "spec" / "golden-vectors.md"
failures = []


def fail(message):
    failures.append(message)


def markdown_files():
    return [ROOT / "README.md"] + sorted((ROOT / "spec").glob("*.md"))


def load_vector_tool():
    spec = importlib.util.spec_from_file_location("check_vectors", ROOT / "tools" / "check_vectors.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_clauses(text):
    """Every clause R<s>.<n> sits under the heading of section <s> and is defined once."""
    section = None
    defined = {}
    for number, line in enumerate(text.split("\n"), 1):
        heading = re.match(r"^## (\d+)\. ", line)
        if heading:
            section = int(heading.group(1))
        elif line.startswith("## "):
            section = None
        clause = re.match(r"^\s*[-*]?\s*\*\*R(\d+)\.(\d+)\*\*", line)
        if not clause:
            continue
        s, n = int(clause.group(1)), int(clause.group(2))
        if section is None:
            fail(f"protocol.md:{number}: clause R{s}.{n} is outside a numbered section")
        elif s != section:
            fail(f"protocol.md:{number}: clause R{s}.{n} sits under section {section}")
        if (s, n) in defined:
            fail(f"protocol.md:{number}: clause R{s}.{n} is defined twice (first at line {defined[(s, n)]})")
        defined[(s, n)] = number
    sections = sorted({int(m.group(1)) for m in re.finditer(r"^## (\d+)\. ", text, re.M)})
    if sections != list(range(len(sections))):
        fail(f"section headings are not contiguous from 0: {sections}")
    return defined


def check_references(defined):
    count = 0
    for path in markdown_files():
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1):
            for m in re.finditer(r"\bR(\d+)\.(\d+)\b", line):
                count += 1
                if (int(m.group(1)), int(m.group(2))) not in defined:
                    fail(f"{path.relative_to(ROOT)}:{number}: reference {m.group(0)} does not exist")
    return count


def check_links():
    count = 0
    for path in markdown_files():
        text = path.read_text(encoding="utf-8")
        for m in re.finditer(r"\[[^\]]*\]\(([^)\s]+)\)", text):
            target = m.group(1)
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            count += 1
            if not (path.parent / target.split("#")[0]).resolve().exists():
                fail(f"{path.relative_to(ROOT)}: link target {target} does not exist")
    return count


def check_registries(text, tool):
    frames = re.findall(r"^\| (\d+) \| ([A-Z_]+) \| (?:C→S|S→C|both) \|$", text, re.M)
    names = [name for _, name in frames]
    if [int(code) for code, _ in frames] != list(range(1, 20)):
        fail("frame registry in section 2.3 must list codes 1..19 in order")
    golden = re.findall(r"^\| ([A-Z_]+) \| (\d+) \| `[0-9a-f]+` \|$", GOLDEN.read_text(encoding="utf-8").partition("## Variant vectors")[0], re.M)
    golden_names = [name for name, _ in golden]
    if golden_names != names:
        fail(f"golden vector names {golden_names} differ from the frame registry {names}")
    errors = {int(code): int(retry) for code, _symbol, retry in
              re.findall(r"^\| (\d+) \| ([A-Z_]+) \| ([01]) \| ", text, re.M)}
    if errors != tool.ERROR_RETRYABLE:
        only_spec = {k: v for k, v in errors.items() if tool.ERROR_RETRYABLE.get(k) != v}
        only_tool = {k: v for k, v in tool.ERROR_RETRYABLE.items() if errors.get(k) != v}
        fail(f"error registry differs from tools/check_vectors.py: spec {only_spec}, tool {only_tool}")
    return len(frames), len(errors)


def main():
    text = SPEC.read_text(encoding="utf-8")
    defined = check_clauses(text)
    refs = check_references(defined)
    links = check_links()
    frames, errors = check_registries(text, load_vector_tool())
    print(f"Clauses: {len(defined)}; references: {refs}; links: {links}; frame types: {frames}; error codes: {errors}")
    if failures:
        for message in failures:
            print("FAIL:", message, file=sys.stderr)
        return 1
    print("PASS: clause numbering, cross-references, links and registries are consistent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
