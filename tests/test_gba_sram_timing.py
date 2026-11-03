"""A passing clock summary must not hide an unsafe SRAM pin route."""
import csv,importlib.util,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('sram_timing',ROOT/'experiments/gba_coverflow/probe_timing.py')
timing=importlib.util.module_from_spec(spec);spec.loader.exec_module(timing)


class SRAMTimingTests(unittest.TestCase):
    def fixture(self,path,change=None):
        rows=[{'corner':c,'direction':d,'from':'source','to':f'{d}{i}','data_ns':'4.249'}
              for c in sorted(timing.CORNERS) for d,count in (('in',16),('out',37)) for i in range(count)]
        if change:change(rows)
        with path.open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]),delimiter='\t');writer.writeheader();writer.writerows(rows)

    def test_complete_four_corner_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'io.tsv';self.fixture(p)
            self.assertEqual(len(timing.summarize(p)),8)

    def test_single_slow_route_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'io.tsv';self.fixture(p,lambda r:r[0].update(data_ns='4.251'))
            with self.assertRaisesRegex(ValueError,'budget failed'):timing.summarize(p)

    def test_missing_one_pin_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'io.tsv';self.fixture(p,lambda r:r.pop())
            with self.assertRaisesRegex(ValueError,'endpoint coverage'):timing.summarize(p)

    def test_missing_corner_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'io.tsv';self.fixture(p,lambda r:r.__delitem__(slice(0,53)))
            with self.assertRaisesRegex(ValueError,'Four SRAM timing corners'):timing.summarize(p)

    def test_query_preserves_full_compile_reports_and_binds_binary(self):
        with tempfile.TemporaryDirectory() as tmp:
            build=Path(tmp)
            for name in ('src/fpga/build/output_files/ap_core.rbf','src/fpga/build/ap_core.qsf','src/fpga/core/core_constraints.sdc'):
                p=build/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'synthetic')
            report=build/'src/fpga/build/output_files/ap_core.sta.summary';report.write_bytes(b'full compile report')
            self.fixture(build/'sram-io.tsv')
            with patch.object(timing.subprocess,'run',side_effect=lambda *a,**kw:report.write_bytes(b'partial query')):
                timing.run(build,quartus='synthetic-quartus')
            self.assertEqual(report.read_bytes(),b'full compile report')
            (build/'src/fpga/build/output_files/ap_core.rbf').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'does not match'):timing.read(build)


if __name__=='__main__':unittest.main()
