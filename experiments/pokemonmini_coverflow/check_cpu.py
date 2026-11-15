#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Exhaustive native DIV equivalence and actual S1C88 microcode lockstep."""
import argparse, hashlib, importlib.util, json, re, shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('pm_cpu_prepare', HERE/'prepare.py')
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def wsl(path):
    path = Path(path).resolve()
    return '/mnt/'+path.drive[0].lower()+path.as_posix()[2:] if path.drive else path.as_posix()


def build(source, candidate, out):
    source, candidate, out = (Path(x).resolve() for x in (source, candidate, out))
    if out.exists() or not prepare.private_output(out):
        raise ValueError('Fresh private Mini test directory required')
    original = source/'src/fpga/core/rtl'
    rtl = candidate/'src/fpga/core/rtl'
    rom = source/'src/fpga/rom'
    frozen = json.loads((HERE/'upstream-files.json').read_text())
    for row in frozen['files']:
        if row['path'].startswith('src/fpga/core/rtl/') or row['path'].startswith('src/fpga/rom/'):
            assert hashlib.sha256((source/row['path']).read_bytes()).hexdigest() == row['sha256'], row['path']
    for name in ('rom.mem','translation_rom.mem'):
        native=[int(v,16) for v in (rom/name).read_text().split()]
        actual=[int(v,16) for v in (candidate/'src/fpga/rom'/name).read_text().split()]
        assert native == actual[:len(native)] and not any(actual[len(native):])
    micro = [int(x,16) for x in (rom/'rom.mem').read_text().split()]
    table = [int(x,16) for x in (rom/'translation_rom.mem').read_text().split()]
    div_rows = [i for i,v in enumerate(micro) if (v >> 27) & 31 == 21]
    assert div_rows == [503,504] and table[0x1d9] == 501
    assert micro[501:505] == [0x706,0x7c1,0x1a8000000,0x3a800019b]
    out.mkdir(parents=True)
    # The reference declares 768 translation words. Extra zero entries in the
    # synthesized 1024-word RAM cannot be addressed by any native opcode.
    shutil.copytree(rom, out/'rom')
    # Only rename modules/hierarchical names; arithmetic and CPU logic stay exact.
    ref = (original/'alu.sv').read_text()
    ref = re.sub(r'\balu\b','alu_ref',ref[ref.index('module alu'):])
    (out/'alu_ref.sv').write_text(ref,encoding='utf8')
    ref = (original/'s1c88.sv').read_text()
    ref = re.sub(r'\bs1c88\b','s1c88_ref',ref[ref.index('module s1c88'):])
    ref = re.sub(r'\balu\b','alu_ref',ref)
    (out/'s1c88_ref.sv').write_text(ref,encoding='utf8')
    files = [rtl/'alu.sv',rtl/'bcd_addsub.sv',candidate/'src/fpga/core/pm_divide.sv',
             out/'alu_ref.sv',rtl/'s1c88.sv',out/'s1c88_ref.sv',HERE/'tb_cpu.sv']
    rows = [{'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]
    (out/'inputs.json').write_text(json.dumps({'files':rows,'microcode_div_rows':div_rows,
        'clock_hz':31999995,'cpu_enable_interval':16,'division_pipeline_clocks':8,
        'undefined_divzero_result_compared':False},indent=2)+'\n',encoding='utf8')
    script = '#!/bin/bash\nset -eu\nulimit -c 0\ncd "$(dirname "$0")"\n'
    script += 'verilator --binary --timing --top-module tb_pm_cpu --build-jobs 2 -Wno-fatal --Mdir obj -o probe '
    script += ' '.join('"'+wsl(p)+'"' for p in files)+' > build.log 2>&1\n'
    script += './obj/probe > simulation.log 2>&1\ncat simulation.log\n'
    (out/'run.sh').write_text(script,encoding='utf8',newline='\n')
    return out/'run.sh'


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate','out'): p.add_argument('--'+n,type=Path,required=True)
    a = p.parse_args()
    print(build(a.source,a.candidate,a.out))
