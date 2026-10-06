"""Execute the Python code blocks in Markdown documents.

Usage (from the repository root, with the package installed):

    python TESTS/doc_examples.py README.md DOCS/*.md

Each ```python block runs in order. Blocks from one file share a namespace,
so a block may use names defined by an earlier block in the same file, as a
reader working through the document would. The script prints PASS or FAIL
per block and exits with status 1 if any block fails or if no block is found.

pytest does not collect this file (its name does not match test_*.py).
"""
import re
import sys
import traceback

FENCE = re.compile(r"^```python[^\n]*\n(.*?)^```", re.MULTILINE | re.DOTALL)


def run(paths):
    total = failed = 0
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        namespace = {"__name__": "__doc_example__"}
        for number, match in enumerate(FENCE.finditer(text), 1):
            total += 1
            line = text.count("\n", 0, match.start()) + 1
            label = f"{path} block {number} (line {line})"
            try:
                code = compile(match.group(1), f"{path}:{line}", "exec")
                exec(code, namespace)
            except Exception:
                failed += 1
                print(f"FAIL {label}")
                traceback.print_exc()
            else:
                print(f"PASS {label}")
    print(f"{total} blocks, {failed} failed")
    return 1 if failed or not total else 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
