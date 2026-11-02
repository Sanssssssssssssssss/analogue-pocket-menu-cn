#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Prepare a separate CoverFlow backend using a pinned upstream CellRAM driver."""
import argparse,hashlib,json,shutil
from pathlib import Path
from prepare_view import prepare,ROOT,HERE

# The driver is supplied by the same pinned native GBA source used by the
# existing integration. Its full Adam Gastineau MIT notice is retained.
PSRAM_SHA='b9aed3cb12ee298a96e78ad7c26d4657eaa3d970465ffcdc4441dce7022e5c58'


def build(out,source):
    source=Path(source).resolve()
    raw=(source/'src/fpga/pocket/psram.sv').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=PSRAM_SHA:raise ValueError('Pinned CellRAM driver SHA differs')
    out=prepare(out,compact=True)
    s=(out/'coverflow_view.sv').read_text()
    s=s.replace('module coverflow_view #','module coverflow_psram_view #',1)
    s=s.replace('coverflow_line_fetch #','coverflow_line_fetch16 #',1)
    (out/'coverflow_psram_view.sv').write_text(s,encoding='utf8',newline='\n')
    fetch=(HERE/'line_fetch.sv').read_text()
    fetch=fetch.replace('module coverflow_line_fetch #','module coverflow_line_fetch16 #',1)
    needle='cached<=enable && !drop_pending && !invalidate && !new_line && !line_arrived && !fault;'
    if fetch.count(needle)!=1:raise ValueError('DWORD cache anchor changed')
    fetch=fetch.replace(needle,'cached<=0; // One 16-bit physical read per texture sample.')
    (out/'coverflow_line_fetch16.sv').write_text(fetch,encoding='utf8',newline='\n')
    driver=raw.decode().replace('module psram #','module coverflow_psram #',1)
    driver=driver.replace('rtoi','cf_psram_rtoi').replace('CEIL','CF_PSRAM_CEIL').replace('MAX','CF_PSRAM_MAX')
    (out/'coverflow_psram.sv').write_text(driver,encoding='utf8',newline='\n')
    shutil.copy2(HERE/'psram_cache.sv',out/'coverflow_psram_cache.sv')
    proof=json.loads((out/'view-source.json').read_text())
    proof.update({'backend':'Dedicated unused CellRAM die, 128 x 64 KiB cover-only slots',
        'driver_sha256':PSRAM_SHA,'driver_scope':'Pinned upstream timing state machine, identifiers namespaced, CLOCK_SPEED=74.25',
        'transport':'16-bit sample replicated to response DWORD; old DWORD reuse explicitly disabled',
        'hardware_acceptance':'pending; a peripheral model is not board-level timing signoff'})
    (out/'view-source.json').write_text(json.dumps(proof,indent=2)+'\n')
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',required=True);p.add_argument('--gba-source',required=True)
    a=p.parse_args();print(build(a.out,a.gba_source))
