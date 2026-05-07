from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


TRACE_READ_PATTERN = re.compile(
    r"TRACE_READ "
    r"phase=(?P<phase>\S+) "
    r"inode=(?P<inode>\d+) "
    r"sector=(?P<sector>-?\d+) "
    r"absolute_sector=(?P<absolute_sector>-?\d+) "
    r"size=(?P<size>-?\d+) "
    r"source=(?P<source>\S+)"
    r"(?: context=(?P<context>\S+) indirect_level=(?P<indirect_level>-?\d+))?"
)


@dataclass(frozen=True)
class TraceReadEvent:
    phase: str
    inode: int
    sector: int
    absolute_sector: int
    size: int
    source: str
    context: str
    indirect_level: int


def parse_trace_reads(text: str) -> list[TraceReadEvent]:
    events: list[TraceReadEvent] = []

    for line in text.splitlines():
        match = TRACE_READ_PATTERN.search(line)
        if match is None:
            continue
        events.append(
            TraceReadEvent(
                phase=match.group('phase'),
                inode=int(match.group('inode')),
                sector=int(match.group('sector')),
                absolute_sector=int(match.group('absolute_sector')),
                size=int(match.group('size')),
                source=match.group('source'),
                context=match.group('context') or 'block',
                indirect_level=int(match.group('indirect_level') or 0),
            )
        )
    return events


def load_trace_reads(path: Path) -> list[TraceReadEvent]:
    return parse_trace_reads(path.read_text())


def filter_trace_reads(
    events: Iterable[TraceReadEvent],
    *,
    inode: int | None = None,
    phase: str | None = None,
) -> list[TraceReadEvent]:
    filtered = list(events)
    if inode is not None:
        filtered = [event for event in filtered if event.inode == inode]
    if phase is not None:
        filtered = [event for event in filtered if event.phase == phase]
    return filtered


def format_event(index: int, event: TraceReadEvent) -> str:
    return (
        f"{index:02d}. phase={event.phase} inode={event.inode} "
        f"sector={event.sector} absolute_sector={event.absolute_sector} "
        f"source={event.source} context={event.context} "
        f"indirect_level={event.indirect_level} size={event.size}"
    )


def summarize_trace(events: Sequence[TraceReadEvent]) -> str:
    lines = [f"events={len(events)}"]
    contexts: dict[tuple[str, int], int] = {}

    for event in events:
        key = (event.context, event.indirect_level)
        contexts[key] = contexts.get(key, 0) + 1

    if contexts:
        lines.append('contexts=')
        for context, indirect_level in sorted(contexts):
            count = contexts[(context, indirect_level)]
            lines.append(
                f"  {context} indirect_level={indirect_level} count={count}"
            )
    lines.append('sequence=')
    for index, event in enumerate(events, start=1):
        lines.append(format_event(index, event))
    return '\n'.join(lines)


def compare_traces(left: Sequence[TraceReadEvent], right: Sequence[TraceReadEvent]) -> str:
    lines = [f"left_events={len(left)}", f"right_events={len(right)}"]
    mismatch_index: int | None = None
    mismatch_pair: tuple[TraceReadEvent, TraceReadEvent] | None = None

    for index, (left_event, right_event) in enumerate(zip(left, right), start=1):
        if left_event != right_event:
            mismatch_index = index
            mismatch_pair = (left_event, right_event)
            break

    if mismatch_index is None and len(left) == len(right):
        lines.append('sequence_match=yes')
        return '\n'.join(lines)

    lines.append('sequence_match=no')
    if mismatch_index is None:
        mismatch_index = min(len(left), len(right)) + 1
        lines.append(f'first_difference_index={mismatch_index}')
        if len(left) > len(right):
            lines.append(f'left_extra={format_event(mismatch_index, left[mismatch_index - 1])}')
        else:
            lines.append(f'right_extra={format_event(mismatch_index, right[mismatch_index - 1])}')
        return '\n'.join(lines)

    lines.append(f'first_difference_index={mismatch_index}')
    lines.append(f'left={format_event(mismatch_index, mismatch_pair[0])}')
    lines.append(f'right={format_event(mismatch_index, mismatch_pair[1])}')
    return '\n'.join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description='Summarize or compare TRACE_READ output from the host-ported original fsck.')
    subparsers = parser.add_subparsers(dest='command', required=True)

    summary_parser = subparsers.add_parser('summary', help='Summarize one trace log.')
    summary_parser.add_argument('trace_log', type=Path)
    summary_parser.add_argument('--inode', type=int)
    summary_parser.add_argument('--phase')

    compare_parser = subparsers.add_parser('compare', help='Compare two trace logs by read sequence.')
    compare_parser.add_argument('left_trace_log', type=Path)
    compare_parser.add_argument('right_trace_log', type=Path)
    compare_parser.add_argument('--inode', type=int)
    compare_parser.add_argument('--phase')

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == 'summary':
        events = filter_trace_reads(load_trace_reads(args.trace_log), inode=args.inode, phase=args.phase)
        print(summarize_trace(events))
        return 0

    left_events = filter_trace_reads(load_trace_reads(args.left_trace_log), inode=args.inode, phase=args.phase)
    right_events = filter_trace_reads(load_trace_reads(args.right_trace_log), inode=args.inode, phase=args.phase)
    print(compare_traces(left_events, right_events))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())