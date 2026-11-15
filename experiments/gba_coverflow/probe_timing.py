#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Check every fitted cover-SRAM I/O route against the simulated 4.25 ns budget."""
import argparse,csv,hashlib,json,shutil,subprocess
from pathlib import Path

HERE=Path(__file__).resolve().parent
CORNERS={'8_slow_1100mv_85c','8_slow_1100mv_0c','MIN_fast_1100mv_85c','MIN_fast_1100mv_0c'}
IO_BUDGET_NS=4.25


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def summarize(path):
    with path.open(newline='') as stream:rows=list(csv.DictReader(stream,delimiter='\t'))
    if {r['corner'] for r in rows}!=CORNERS:raise ValueError('Four SRAM timing corners required')
    summary=[]
    for corner in sorted(CORNERS):
        for direction,expected in (('in',16),('out',37)):
            group=[r for r in rows if r['corner']==corner and r['direction']==direction]
            endpoints={r['to'] for r in group}
            if len(endpoints)!=expected:raise ValueError(f'Incomplete {corner} {direction} endpoint coverage: {len(endpoints)}')
            values=[float(r['data_ns']) for r in group]
            if not all(0<=n<=IO_BUDGET_NS for n in values):raise ValueError(f'SRAM {IO_BUDGET_NS}ns data budget failed: {corner} {direction} max={max(values)}')
            summary.append({'corner':corner,'direction':direction,'endpoints':len(endpoints),'paths':len(group),'maximum_data_ns':max(values)})
    return summary


def bindings(build):
    return {name:sha(build/name) for name in (
        'src/fpga/build/output_files/ap_core.rbf','src/fpga/build/ap_core.qsf',
        'src/fpga/core/core_constraints.sdc')}


def read(build):
    build=Path(build).resolve()
    receipt=json.loads((build/'sram-io-receipt.json').read_text())
    if receipt.get('inputs')!=bindings(build) or receipt.get('checker_sha256')!=sha(HERE/'check_sram_timing.tcl'):
        raise ValueError('SRAM timing receipt does not match fitted inputs/checker')
    if receipt.get('report_sha256')!=sha(build/'sram-io.tsv'):raise ValueError('SRAM timing report changed')
    if receipt.get('budget_ns')!=IO_BUDGET_NS or receipt.get('model_sha256')!=sha(HERE/'sim_sram.sv'):
        raise ValueError('SRAM timing budget/model changed')
    if receipt.get('summary')!=summarize(build/'sram-io.tsv'):raise ValueError('SRAM timing receipt summary changed')
    return receipt


def run(build,quartus=None,image=None):
    build=Path(build).resolve()
    receipt=build/'sram-io-receipt.json'
    if receipt.exists():raise ValueError('Timing receipt already exists; use read() to verify it')
    shutil.copy2(HERE/'check_sram_timing.tcl',build/'check_sram_timing.tcl')
    if image:
        command=['docker','run','--rm','--network','none','--cpus','2','--memory','4g','-v',str(build)+':/build',
                 '-w','/build/src/fpga/build','--entrypoint','/opt/intelFPGA/quartus/bin/quartus_sta',image,'-t','/build/check_sram_timing.tcl']
    else:command=[quartus or 'quartus_sta','-t',str(build/'check_sram_timing.tcl')]
    # Quartus -t replaces the standard STA reports even for a custom query.
    # Retain the full compile's original reports for the independent packager.
    outputs=build/'src/fpga/build/output_files'
    reports={p:p.read_bytes() for p in outputs.glob('ap_core.sta.*') if p.is_file()}
    try:
        with (build/'sram-io.log').open('w') as stream:
            subprocess.run(command,cwd=build/'src/fpga/build',stdout=stream,stderr=subprocess.STDOUT,timeout=240,check=True)
    finally:
        for path,content in reports.items():path.write_bytes(content)
    result={'scope':'Post-fit data paths for all 37 output and 16 input endpoints at all four device corners; 4.25ns maximum excluding clock insertion',
            'budget_ns':IO_BUDGET_NS,'model_sha256':sha(HERE/'sim_sram.sv'),
            'inputs':bindings(build),'checker_sha256':sha(HERE/'check_sram_timing.tcl'),
            'report_sha256':sha(build/'sram-io.tsv'),'summary':summarize(build/'sram-io.tsv')}
    receipt.write_text(json.dumps(result,indent=2)+'\n')
    return read(build)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',required=True)
    g=p.add_mutually_exclusive_group();g.add_argument('--quartus-sta');g.add_argument('--docker-image')
    a=p.parse_args();print(json.dumps(run(a.build,a.quartus_sta,a.docker_image),indent=2))
