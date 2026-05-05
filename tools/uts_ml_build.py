#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Build uts/i386/ml machine-layer objects.')
    parser.add_argument('--workspace-root', required=True)
    parser.add_argument('--obj-root', required=True)
    parser.add_argument('--pack-root', required=True)
    parser.add_argument('--cc', required=True)
    parser.add_argument('--cpp', required=True)
    parser.add_argument('--ld', required=True)
    parser.add_argument('--cflag', action='append', default=[])
    parser.add_argument('--cpp-flag', action='append', default=[])
    parser.add_argument('--ld-flag', action='append', default=[])
    return parser.parse_args()


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    rendered = ' '.join(command)
    print(f'    {rendered}')
    subprocess.run(command, cwd=cwd, env=env, check=True)


def compile_generated_assembly(cc: str, cflags: list[str], source: Path, output: Path, cwd: Path) -> None:
    run([cc, *cflags, '-c', str(source), '-o', str(output)], cwd=cwd)


def sanitize_symvals_assembly(work_ml_root: Path) -> None:
    source = work_ml_root / 'symvals.s'
    lines = source.read_text(encoding='utf-8').splitlines()
    filtered = [line for line in lines if line not in {'#APP', '#NO_APP'}]
    source.write_text('\n'.join(filtered) + '\n', encoding='utf-8')


def sanitize_symvals_header(work_ml_root: Path) -> None:
    source = work_ml_root / 'symvals.h'
    filtered: list[str] = []
    for line in source.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped:
            filtered.append('')
            continue
        if not stripped.startswith('#define'):
            continue
        if stripped.endswith('\\'):
            continue
        filtered.append(line)
    source.write_text('\n'.join(filtered) + '\n', encoding='utf-8')


def write_locore_source(work_ml_root: Path) -> Path:
    output = work_ml_root / 'locore-temp.c'
    inputs = [
        work_ml_root / 'symvals.s',
        work_ml_root / 'ttrap.s',
        work_ml_root / 'cswitch.s',
        work_ml_root / 'misc.s',
        work_ml_root / 'intr.s',
        work_ml_root / 'weitek.s',
        work_ml_root / 'v86gptrap.s',
        work_ml_root / 'oemsup.s',
        work_ml_root / 'string.s',
    ]
    with output.open('w', encoding='utf-8') as handle:
        handle.write('\t.file\t"locore.s"\n')
        for source in inputs:
            content = source.read_text(encoding='utf-8')
            handle.write(content)
            if not content.endswith('\n'):
                handle.write('\n')
    return output


def write_start_source(work_ml_root: Path) -> Path:
    output = work_ml_root / 'start-temp.c'
    inputs = [work_ml_root / 'symvals.s', work_ml_root / 'uprt.s']
    with output.open('w', encoding='utf-8') as handle:
        handle.write('\t.file\t"uprt.s"\n')
        for source in inputs:
            content = source.read_text(encoding='utf-8')
            handle.write(content)
            if not content.endswith('\n'):
                handle.write('\n')
    return output


def rewrite_tables2_assembly(work_ml_root: Path) -> Path:
    source = work_ml_root / 'tables2.s'
    output = work_ml_root / 'tables2-temp.s'
    lines = source.read_text(encoding='utf-8').splitlines()
    with output.open('w', encoding='utf-8') as handle:
        for line in lines:
            if line == '\t.data':
                handle.write('\t.text\n')
                handle.write('\t.align\t8\n')
                continue
            handle.write(f'{line}\n')
    return output


def prepare_worktree(source_root: Path, obj_root: Path) -> Path:
    work_root = obj_root / '_workroot'
    if work_root.exists():
        shutil.rmtree(work_root)
    work_root.mkdir(parents=True)
    for name in ('sys', 'vm'):
        (work_root / name).symlink_to(source_root / name, target_is_directory=True)
    shutil.copytree(source_root / 'ml', work_root / 'ml')
    return work_root / 'ml'


def main() -> int:
    args = parse_args()
    workspace_root = Path(args.workspace_root).resolve()
    obj_root = Path(args.obj_root).resolve()
    pack_root = Path(args.pack_root).resolve()
    uts_root = workspace_root / 'uts' / 'i386'
    ml_root = uts_root / 'ml'

    obj_root.mkdir(parents=True, exist_ok=True)
    pack_root.mkdir(parents=True, exist_ok=True)

    work_ml_root = prepare_worktree(uts_root, obj_root)

    env = dict(os.environ)
    env['CC'] = args.cc
    env['CFLAGS'] = ' '.join(args.cflag)
    env['INCRT'] = '..'

    run(['sh', 'Gensymvals', f'CC={args.cc}', f'CFLAGS={" ".join(args.cflag)}', 'INCRT=..'], cwd=work_ml_root, env=env)
    sanitize_symvals_assembly(work_ml_root)
    sanitize_symvals_header(work_ml_root)

    for source_name in ('tables1.c', 'pit.c', 'pic.c'):
        output = obj_root / f'{Path(source_name).stem}.o'
        run([args.cc, *args.cflag, '-c', source_name, '-o', str(output)], cwd=work_ml_root)

    run([args.cc, *args.cflag, '-S', 'tables2.c', '-o', 'tables2.s'], cwd=work_ml_root)
    tables2_temp = rewrite_tables2_assembly(work_ml_root)
    tables2_obj = obj_root / 'tables2.o'
    compile_generated_assembly(args.cc, args.cflag, tables2_temp, tables2_obj, work_ml_root)

    syms_source = work_ml_root / 'syms-preprocessed.s'
    run([args.cc, '-x', 'assembler-with-cpp', '-E', *args.cpp_flag, 'syms.s', '-o', str(syms_source)], cwd=work_ml_root)
    syms_obj = obj_root / 'syms.o'
    compile_generated_assembly(args.cc, args.cflag, syms_source, syms_obj, work_ml_root)

    locore_temp = write_locore_source(work_ml_root)
    locore_source = work_ml_root / 'locore.s'
    run([args.cc, '-x', 'assembler-with-cpp', '-E', *args.cpp_flag, str(locore_temp), '-o', str(locore_source)], cwd=work_ml_root)
    locore_asm_obj = work_ml_root / 'locore-asm.o'
    compile_generated_assembly(args.cc, args.cflag, locore_source, locore_asm_obj, work_ml_root)

    locore_obj = obj_root / 'locore.o'
    run(
        [
            args.ld,
            *args.ld_flag,
            '-r',
            '-o',
            str(locore_obj),
            str(obj_root / 'tables1.o'),
            str(locore_asm_obj),
            str(obj_root / 'pit.o'),
            str(obj_root / 'pic.o'),
        ],
        cwd=work_ml_root,
    )

    start_temp = write_start_source(work_ml_root)
    start_source = work_ml_root / 'start.s'
    run([args.cc, '-x', 'assembler-with-cpp', '-E', *args.cpp_flag, str(start_temp), '-o', str(start_source)], cwd=work_ml_root)
    start_asm_obj = work_ml_root / 'start-asm.o'
    compile_generated_assembly(args.cc, args.cflag, start_source, start_asm_obj, work_ml_root)

    start_obj = obj_root / 'start.o'
    run(
        [
            args.ld,
            *args.ld_flag,
            '-r',
            '-o',
            str(start_obj),
            str(start_asm_obj),
            str(tables2_obj),
        ],
        cwd=work_ml_root,
    )

    for output in (locore_obj, start_obj, syms_obj):
        shutil.copy2(output, pack_root / output.name)

    return 0


if __name__ == '__main__':
    raise SystemExit(main())