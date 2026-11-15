#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Group installed Pocket Lab menus using official platform categories."""
import argparse
import copy
from pathlib import Path
import shutil

from apf_metadata import check_core
from build_library import sha
from delivery import read, write, separate
from install import identity, publish, safe_path

CATEGORY = 'CN Menu'


def apply(card, backup):
    card, backup = Path(card).resolve(), Path(backup).resolve()
    separate(card, backup)
    if backup.exists():
        raise ValueError('Use a fresh external backup directory')
    ident = identity(card)
    changes, guards, seen = [], [], set()
    for folder in sorted(safe_path(card, 'Cores').glob('pocketlab.*')):
        safe_path(card, folder.relative_to(card).as_posix())
        core = check_core(folder)
        if core['metadata']['author'] != 'pocketlab':
            raise ValueError('Unexpected author in a Pocket Lab core')
        platform = core['metadata']['platform_ids'][0]
        rel = 'Platforms/'+platform+'.json'
        source = safe_path(card, rel)
        before = read(source)
        if rel in seen:
            raise ValueError('Two menu cores share a primary platform')
        seen.add(rel)
        for name in ('core.json', 'data.json', 'video.json', 'input.json'):
            p = safe_path(card, folder.relative_to(card).as_posix()+'/'+name)
            guards.append({'path':p.relative_to(card).as_posix(), 'sha256':sha(p)})
        if before['platform'].get('category') == CATEGORY:
            continue
        after = copy.deepcopy(before)
        after['platform']['category'] = CATEGORY
        changes.append({'path':rel, 'before':before, 'after':after, 'previous_sha256':sha(source)})
    if not seen:
        raise ValueError('No installed Pocket Lab menus found')
    backup.mkdir(parents=True)
    for row in changes:
        rel = row['path']
        previous = safe_path(backup/'previous', rel)
        previous.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe_path(card, rel), previous)
        if sha(previous) != row['previous_sha256']:
            raise ValueError('Backup verification failed: '+rel)
        write(safe_path(backup/'updated', rel), row['after'])
        row['sha256'] = sha(safe_path(backup/'updated', rel))
    receipt = {'identity':ident, 'category':CATEGORY, 'changes':changes, 'guards':guards,
               'status':'backed_up_before_writes', 'core_writes':0, 'save_writes':0, 'firmware_writes':0,
               'usage':'Settings > Analogue OS > Group openFPGA: On'}
    write(backup/'group-receipt.json', receipt)
    try:
        for row in changes:
            if identity(card) != ident or sha(safe_path(card, row['path'])) != row['previous_sha256']:
                raise ValueError('Card or category changed after preparation')
            publish(safe_path(backup/'updated', row['path']), safe_path(card, row['path']), row['sha256'])
        for row in guards:
            if sha(safe_path(card, row['path'])) != row['sha256']:
                raise ValueError('Core or asset binding changed during grouping')
    except (OSError, ValueError):
        restore(card, backup)
        raise
    receipt['status'] = 'installed_readback_verified_group_view_pending'
    write(backup/'group-receipt.json', receipt)
    return {'platforms':len(seen), 'files_changed':len(changes), 'backup':str(backup), 'category':CATEGORY}


def restore(card, backup):
    card, backup = Path(card).resolve(), Path(backup).resolve()
    separate(card, backup)
    receipt = read(backup/'group-receipt.json')
    if identity(card) != receipt['identity']:
        raise ValueError('Different Pocket card')
    for row in receipt['changes']:
        rel = row['path']
        if Path(rel).parts[0] != 'Platforms' or len(Path(rel).parts) != 2 or not rel.endswith('.json'):
            raise ValueError('Restore is limited to platform definitions')
        if sha(safe_path(card, rel)) not in (row['previous_sha256'], row['sha256']):
            raise ValueError('Platform changed since grouping: '+rel)
        if sha(safe_path(backup/'previous', rel)) != row['previous_sha256']:
            raise ValueError('Original category backup changed')
    for row in receipt['changes']:
        if identity(card) != receipt['identity']:
            raise ValueError('Card changed during restore')
        publish(safe_path(backup/'previous', row['path']), safe_path(card, row['path']), row['previous_sha256'])
    receipt['status'] = 'original_categories_restored'
    write(backup/'group-receipt.json', receipt)
    return {'files_restored':len(receipt['changes']), 'core_writes':0, 'save_writes':0}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('apply', 'restore'))
    parser.add_argument('--card', required=True)
    parser.add_argument('--backup', required=True)
    args = parser.parse_args()
    print((apply if args.action == 'apply' else restore)(args.card, args.backup))
