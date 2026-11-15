#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Single-job desktop workflow using the same checked CLI build/install path."""
from datetime import datetime
from pathlib import Path
import shutil
import threading
import uuid

import build_menus
import compatibility
import delivery
import library_catalog
import progress_import
import additional_menus

LABELS = {'GB-GBC': 'GB / GBC', 'GBA': 'GBA', 'NES': 'FC / NES', 'GG': 'Game Gear',
          'SMS': 'Master System', 'SG1000': 'SG-1000', 'PCE': 'PCE / SuperGrafx',
          'MD': 'Mega Drive', 'SFC': 'SFC / SNES', 'CPS2': 'CPS2'}
LABELS.update({name: row['label'] for name,row in additional_menus.PROFILES.items()})
COMPAT_LABELS = {'SFC-COMPAT': 'SFC 特殊卡带', 'PCE-CD': 'PC Engine CD', 'MD-PAL': 'MD PAL',
                 'GBA-MEMORIES': 'GBA 即时存档原版入口', 'GBA-CHEATS': 'GBA 金手指原版入口'}
LOCK = threading.Lock()


def detect_cards():
    import os
    roots = [Path(f'{chr(letter)}:/') for letter in range(ord('D'), ord('Z')+1)] if os.name == 'nt' else []
    found = []
    for root in roots:
        try:
            if (root/'Analogue_Pocket.json').is_file():
                found.append(delivery.identity(root))
        except (OSError, ValueError):
            pass
    return found


class Workflow:
    def __init__(self, packages, work, progress=None):
        self.packages = Path(packages).resolve()
        self.work = Path(work).resolve()
        self.progress = progress or (lambda message: None)
        self.session = self.card = self.config = self.staging = self.prepared_identity = None

    def inspect(self, card):
        card = Path(card).resolve()
        if not delivery.safe_path(card, 'Analogue_Pocket.json').is_file():
            raise ValueError('Select the Pocket card root containing Analogue_Pocket.json')
        ident = delivery.identity(card)
        delivery.separate(card, self.work)
        delivery.separate(card, self.packages)
        if self.work.exists() and not self.work.is_dir():
            raise ValueError('The work directory is an existing file')
        found = build_menus.discover(card)
        packages = {}
        package_errors = {}
        for name in found:
            package = self.packages/name
            packages[name] = package.is_dir()
            if packages[name] and name in additional_menus.PROFILES:
                try:
                    additional_menus.registered(package, name)
                except (OSError, ValueError, KeyError, TypeError) as exc:
                    packages[name] = False
                    package_errors[name] = str(exc)
        return {'identity': ident, 'systems': {name: len(paths) for name, paths in found.items()},
                'packages': packages, 'package_errors': package_errors,
                'compatibility': compatibility.scan(card, found)}

    def prepare(self, card, systems, *, online=True, titles=None, covers=None, bios=None,
                cheats=None, skip_invalid=True, save_import=None, companions=True, gba_modes=()):
        if not LOCK.acquire(blocking=False):
            raise ValueError('Another library task is running; wait for it to finish')
        try:
            self.staging = None
            self.card = Path(card).resolve()
            inspected = self.inspect(self.card)
            if any(not inspected['packages'].get(s) for s in systems):
                raise ValueError('Selected system has no ROMs or no matching package')
            if 'GBA' in systems:
                gba_bios = delivery.safe_path(self.card, compatibility.GBA_BIOS)
                if not gba_bios.is_file() or gba_bios.stat().st_size != 16384:
                    raise ValueError('Provide your own 16384-byte GBA BIOS in Assets/gba/common/gba_bios.bin')
            self.session = self.work/'runs'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:6])
            self.session.mkdir(parents=True)
            scan = inspected['compatibility']
            components, report = compatibility.prepare(
                self.card, scan, self.work/'cache/upstream-cores', online, systems,
                detected=companions, gba_modes=gba_modes)
            self.companions = {'scan': scan, 'entries': report}
            delivery.write(self.session/'compatibility-report.json', self.companions)
            supported = {'SFC': scan['standard_sfc'], 'MD': scan['standard_md']}
            native = [system for system in systems if supported.get(system, 1)]
            self.config = self.session/'library/delivery.json'
            if native:
                self.progress('正在匹配中文名称和封面。')
                self.metadata = library_catalog.enrich(self.card, self.session/'metadata', self.work/'cache', native,
                    online=online, local_titles=titles, local_covers=covers,
                    progress=lambda n, total, title: self.progress(f'图文 {n}/{total}  {title}'))
                self.progress('正在生成各机种的封面菜单。')
                self.menus = build_menus.build(self.card, self.session/'library', native,
                    self.session/'metadata/titles.json', self.session/'metadata/covers', bios, skip_invalid, cheats,
                    packages=self.packages)
                config = delivery.read(self.config)
            else:
                self.metadata = {'matched_titles': 0, 'matched_covers': 0, 'missing_covers': [], 'errors': [],
                                 'offline_cache_misses': []}
                self.menus = {'systems': {}}
                config = {'components': []}
            config['components'].extend(components)
            if not config['components']:
                summary = {'status': 'no_install', 'session': str(self.session), 'compatibility': self.companions}
                delivery.write(self.session/'assistant-report.json', summary)
                return summary
            if save_import is not None:
                config['save_import'] = save_import
            delivery.write(self.config, config)
            return self._prepare_plan()
        finally:
            LOCK.release()

    def _prepare_plan(self):
        self.progress('正在核对存档来源、核心文件和安装目标。')
        target = self.session/('stage-'+uuid.uuid4().hex[:6])
        try:
            plan = delivery.prepare(self.card, self.config, target)
        except progress_import.Conflict as exc:
            self.staging = None
            return {'status': 'save_conflict', 'report': exc.report, 'session': str(self.session)}
        self.staging = target
        self.prepared_identity = plan['identity']
        migration = delivery.read(target/'save-import-report.json') if (target/'save-import-report.json').exists() else None
        summary = {'status': 'ready', 'session': str(self.session), 'staging': str(target),
                   'identity': plan['identity'], 'systems': list(plan['components']), 'writes': len(plan['changes']),
                   'bytes': sum(row['bytes'] for row in plan['changes']), 'metadata': {
                       key: self.metadata[key] for key in ('matched_titles', 'matched_covers', 'missing_covers',
                                                           'errors', 'offline_cache_misses')},
                   'save_import': migration, 'menus': self.menus, 'compatibility': self.companions,
                   'card_free_bytes': shutil.disk_usage(self.card).free,
                   'card_required_bytes': delivery.publication_space(self.card, plan['changes']) + 32*1024**2}
        delivery.write(self.session/'assistant-report.json', summary)
        return summary

    def resolve_saves(self, choices):
        with LOCK:
            if self.config is None or self.staging is not None:
                raise ValueError('No unresolved preparation is available')
            config = delivery.read(self.config)
            config['save_import']['choices'] = choices
            delivery.write(self.config, config)
            return self._prepare_plan()

    def install(self):
        with LOCK:
            if self.staging is None or delivery.identity(self.card) != self.prepared_identity:
                raise ValueError('Prepare the currently connected card before installing')
            self.progress('正在备份菜单和普通存档；备份核对通过后才会写入。')
            backup = self.work/'backups'/self.session.name
            result = delivery.apply(self.card, self.staging, backup)
            self.staging = None
            self.progress('文件已写入并回读校验通过。')
            return {'status': result['status'], 'backup': str(backup), 'session': str(self.session),
                    'writes': len(result['changes']), 'hardware_acceptance': 'pending'}

    def restore(self, card, backup):
        with LOCK:
            self.staging = None
            delivery.rollback(card, backup)
            return delivery.rollback(card, backup, execute=True)
