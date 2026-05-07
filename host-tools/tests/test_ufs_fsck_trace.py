from __future__ import annotations

import unittest

from host_tools.fs.ufs_fsck_trace import compare_traces, parse_trace_reads


class UfsFsckTraceTests(unittest.TestCase):
    def test_parse_trace_reads_includes_context_and_indirect_level(self) -> None:
        events = parse_trace_reads(
            '\n'.join(
                [
                    'noise before trace',
                    'TRACE_READ phase=pass1 inode=5 sector=169904 absolute_sector=170282 size=4096 source=getblk context=indirect indirect_level=2',
                ]
            )
        )

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].phase, 'pass1')
        self.assertEqual(events[0].inode, 5)
        self.assertEqual(events[0].sector, 169904)
        self.assertEqual(events[0].absolute_sector, 170282)
        self.assertEqual(events[0].context, 'indirect')
        self.assertEqual(events[0].indirect_level, 2)

    def test_compare_traces_reports_first_difference(self) -> None:
        left = parse_trace_reads(
            '\n'.join(
                [
                    'TRACE_READ phase=pass1 inode=5 sector=169768 absolute_sector=170146 size=4096 source=getblk context=indirect indirect_level=1',
                    'TRACE_READ phase=pass1 inode=5 sector=169904 absolute_sector=170282 size=4096 source=getblk context=indirect indirect_level=2',
                ]
            )
        )
        right = parse_trace_reads(
            '\n'.join(
                [
                    'TRACE_READ phase=pass1 inode=5 sector=169768 absolute_sector=170146 size=4096 source=getblk context=indirect indirect_level=1',
                    'TRACE_READ phase=pass1 inode=5 sector=169912 absolute_sector=170290 size=4096 source=getblk context=indirect indirect_level=2',
                ]
            )
        )

        comparison = compare_traces(left, right)

        self.assertIn('sequence_match=no', comparison)
        self.assertIn('first_difference_index=2', comparison)
        self.assertIn('sector=169904', comparison)
        self.assertIn('sector=169912', comparison)


if __name__ == '__main__':
    unittest.main()