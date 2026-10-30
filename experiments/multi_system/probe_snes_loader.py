#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Assemble the unmodified SNES loader and exercise its actual VM decisions."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from fixtures import snes


def run(sources, bass, simulator, out):
    out = Path(out).resolve()
    if out.exists(): raise ValueError('Use a new local output directory')
    out.mkdir(parents=True)
    support = Path(sources)/'snes/support'
    for p in support.glob('*.asm'): shutil.copy2(p, out/p.name)
    subprocess.run([str(Path(bass).resolve()), 'loader.asm'], cwd=out, check=True, timeout=30)
    cases = [('lorom', {}, 0, 0), ('hirom', {'kind':'hirom'}, 0, 0),
             ('exhirom', {'kind':'exhirom'}, 0, 0), ('pal', {'pal':True}, 2, 0),
             ('sdd1', {'chip':0x43}, 1, 0), ('spc7110', {'chip':0xF9}, 1, 0),
             ('copier-header', {'copier':True}, 0, 512)]
    records = []
    for name, kwargs, core, offset in cases:
        folder = out/name; folder.mkdir()
        (folder/'rom.fixture').write_bytes(snes(**kwargs))
        (folder/'save.fixture').write_bytes(bytes(8192))
        (folder/'data.json').write_text(json.dumps({'data':{'data_slots':[
            {'id':0, 'filename':'rom.fixture'}, {'id':10, 'filename':'save.fixture'}]}}))
        command = [str(Path(simulator).resolve()), '--bin', str(out/'loader.bin'),
                   '--data-json', str(folder/'data.json'), '--json']
        result = subprocess.run(command, capture_output=True, text=True, timeout=45)
        (folder/'stderr.txt').write_text(result.stderr)
        data = json.loads(result.stdout)
        # VM JSON includes the complete open fixture: keep only useful evidence.
        (folder/'trace.json').write_text(json.dumps({'core':data['core'],'logs':data['logs']}, indent=2))
        chosen = [int(m[1], 16) for line in data['logs']
                  if (m := re.search(r'Selected core (0x[\da-fA-F]+)', line))]
        assert result.returncode == 0 and chosen[-1] == core, (name, result.returncode, chosen)
        offsets = [int(m[1], 16) for line in data['logs']
                   if (m := re.search(r'Adjusting offset of file 0x0 to (0x[\da-fA-F]+)', line))]
        loads = [int(m[1], 16) for line in data['logs']
                 if (m := re.search(r'Loading file (0x[\da-fA-F]+) into FPGA', line))]
        assert offsets == [offset] and loads == [0, 10], (name, offsets, loads)
        expected_chip = {'lorom':0, 'hirom':1, 'exhirom':2, 'pal':0,
                         'sdd1':0x50, 'spc7110':0xD8, 'copier-header':0}[name]
        chips = [int(m[1],16) for line in data['logs']
                 if (m := re.search(r'pmpw write (0x[\da-fA-F]+) to FPGA memory at 0x8$',line))]
        assert chips == [expected_chip], (name, chips)
        records.append({'case': name, 'selected_core': chosen[-1], 'expected_core':core,
                        'chip_type':expected_chip, 'copier_bytes':offset,
                        'loaded_slots':loads, 'exit': result.returncode, 'passed':True})
    negative = []
    for name,size in [('64k-end-of-file',65536),('truncated',1024)]:
        folder=out/name;folder.mkdir()
        (folder/'rom.fixture').write_bytes(snes()[:size])
        (folder/'save.fixture').write_bytes(bytes(8192))
        (folder/'data.json').write_text(json.dumps({'data':{'data_slots':[
            {'id':0,'filename':'rom.fixture'},{'id':10,'filename':'save.fixture'}]}}))
        result=subprocess.run([str(Path(simulator).resolve()),'--bin',str(out/'loader.bin'),
            '--data-json',str(folder/'data.json'),'--json'],capture_output=True,text=True,timeout=45)
        data=json.loads(result.stdout)
        (folder/'trace.json').write_text(json.dumps({'core':data['core'],'logs':data['logs']},indent=2))
        assert result.returncode==1 and data['core'] is None, (name,result.returncode,data['core'])
        assert any('past end of file' in line for line in data['logs']), name
        negative.append({'case':name,'result':'VM refused file before core selection',
                         'hardware_behavior':'not tested'})
    receipt = {'scope':'Actual upstream Chip32 bytecode, synthetic files; host and FPGA operations are VM stubs',
               'hardware_validated':False, 'game_execution_validated':False,
               'loader_sha256':hashlib.sha256((out/'loader.bin').read_bytes()).hexdigest(),
               'cases':records, 'boundary_observations':negative}
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for flag in ('sources','bass','simulator','out'): p.add_argument('--'+flag, required=True)
    a = p.parse_args(); run(a.sources,a.bass,a.simulator,a.out)
