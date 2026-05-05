#!/usr/bin/env python3

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def find_comment_index(line: str) -> int:
    quote: str | None = None
    for index, char in enumerate(line):
        if char in {'"', "'"}:
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
            continue
        if char == '/' and quote is None:
            if index == 0 or line[:index].strip() == '' or line[index - 1].isspace():
                return index
    return -1


def rewrite_legacy_comment_syntax(source_text: str) -> str:
    rewritten: list[str] = []
    for line in source_text.splitlines():
        comment_index = find_comment_index(line)
        if comment_index == -1:
            rewritten.append(line.replace('\\*', '*'))
            continue
        normalized = f'{line[:comment_index]}#{line[comment_index + 1:]}'
        rewritten.append(normalized.replace('\\*', '*'))
    return '\n'.join(rewritten) + '\n'


def main() -> int:
    args = sys.argv[1:]
    real_as = '/usr/bin/as'
    if not Path(real_as).exists():
        resolved = shutil.which('as')
        if not resolved:
            raise SystemExit('error: could not locate system assembler')
        real_as = resolved

    source_index = None
    for index in range(len(args) - 1, -1, -1):
        if not args[index].startswith('-'):
            source_index = index
            break

    temp_path: Path | None = None
    if source_index is not None:
        source_path = Path(args[source_index])
        if source_path.suffix in {'.s', '.S', '.i'} and source_path.exists():
            temp_file = tempfile.NamedTemporaryFile('w', suffix=source_path.suffix, delete=False)
            temp_path = Path(temp_file.name)
            temp_file.write(rewrite_legacy_comment_syntax(source_path.read_text(encoding='utf-8', errors='replace')))
            temp_file.close()
            args[source_index] = str(temp_path)

    command = [real_as]
    if '--32' not in args:
        command.append('--32')
    command.extend(args)
    try:
        subprocess.run(command, check=True)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())