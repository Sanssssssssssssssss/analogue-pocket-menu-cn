#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Chinese desktop assistant; ROMs, BIOS and progress are supplied locally."""
import argparse
import json
import os
from pathlib import Path
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import assistant_workflow as workflow
import delivery


def friendly_error(message):
    lower = message.lower()
    if ('identity changed' in lower or 'different card' in lower or 'destination changed' in lower
            or 'inventory changed after preparation' in lower):
        return '卡、游戏或目标文件在准备后发生了变化。请重新识别当前卡并准备。'
    if 'analogue_pocket.json' in lower or 'expected an analogue pocket card root' in lower:
        return '请选择 Pocket 卡的根目录或它的完整副本。若是新卡，先让 Pocket 初始化，再接回电脑。'
    if 'gba_bios.bin' in lower or '16384-byte bios' in lower:
        return '请将你自己的 16 KiB GBA BIOS 放到卡的 Assets/gba/common/gba_bios.bin，然后重新准备。'
    if 'system card bios 容量' in lower:
        return message+'。请核对卡上 Assets/pcecd/common 的 BIOS。'
    if 'system card bios' in lower:
        return '请将你自己的 System Card BIOS 放在卡的 Assets/pcecd/common。例如 bios_3_0_usa.pce。'
    if 'bios' in lower:
        return '缺少所需 BIOS，或 BIOS 与现有库不一致。请在“图文、金手指与旧存档”页选择自己的 BIOS，并查看本次报告。'
    if 'existing target' in lower and ('save' in lower or 'rtc' in lower):
        return '当前已有存档的容量或时钟格式不正确，已停止安装并保留文件。详细路径见本次报告。'
    if 'separate' in lower or 'outside' in lower:
        return '目录位置有冲突。请把工作目录和备份放在电脑上，与 Pocket 卡、核心包分开。'
    if 'insufficient' in lower:
        return '可用空间不足，已停止操作。请查看电脑工作目录和卡的剩余容量。'
    if 'work directory' in lower:
        return '电脑工作目录不能使用。请选择一个可写入的电脑目录。'
    if 'selected system' in lower or 'no rom' in lower:
        return '选中的机种没有找到支持的游戏或配套核心包。请先识别游戏库，再检查机种列表。'
    if 'fresh' in lower or 'new output' in lower or 'new result' in lower:
        return '这个输出位置已经有文件。请选择一个新目录，保留之前的结果和备份。'
    return '这一步没有完成。原因：'+message


class Assistant:
    def __init__(self, root, packages=None, work=None):
        self.root = root
        self.root.title('Pocket Lab · 游戏库助手')
        root.geometry('1060x800')
        root.minsize(960, 720)
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.events = queue.Queue()
        self.busy = False
        self.engine = self.report = None
        self.last_backup = None
        self.inputs = []
        self.root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style(root)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 21, 'bold'))
        style.configure('Muted.TLabel', foreground='#52656b')
        style.configure('Accent.TButton', font=('Microsoft YaHei UI', 10, 'bold'), padding=(16, 9))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='把游戏库准备好，再去玩。', font=('Microsoft YaHei UI', 21, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='中文名称 · 封面菜单 · 存档迁移 · 备份安装', style='Muted.TLabel').pack(anchor='w', pady=(5, 20))
        origin = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else delivery.ROOT
        self.values = {name: tk.StringVar(value=value) for name, value in {
            'card': '', 'work': str(work or origin/'PocketLab-data'),
            'packages': str(packages or origin/'packages'), 'titles': '', 'covers': '', 'bios': '',
            'cheats': '', 'donor': '', 'donor_roms': '', 'donor_saves': ''}.items()}
        location = ttk.LabelFrame(frame, text='1  选择 Pocket 卡或它的本地副本', padding=12)
        location.pack(fill='x')
        self.path_row(location, '卡目录', 'card', 0)
        self.path_row(location, '电脑工作目录', 'work', 1)
        self.scan = ttk.Button(location, text='识别游戏库', command=self.inspect)
        self.scan.grid(row=0, column=3, padx=(10, 0))
        self.inputs.append(self.scan)
        detect = ttk.Button(location, text='查找已连接的卡', command=self.detect)
        detect.grid(row=1, column=3, padx=(10, 0))
        self.inputs.append(detect)
        self.identity = tk.StringVar(value='工作目录用于缓存、准备文件和备份，请选电脑磁盘上的位置。')
        ttk.Label(location, textvariable=self.identity, style='Muted.TLabel').grid(row=2, column=0, columnspan=4, sticky='w', pady=(8, 0))
        middle = ttk.Frame(frame)
        middle.pack(fill='both', expand=True, pady=(16, 12))
        choices_box = ttk.LabelFrame(middle, text='2  选择要准备的机种', padding=12)
        choices_box.pack(side='left', fill='y', padx=(0, 14))
        choices_canvas = tk.Canvas(choices_box, width=300, highlightthickness=0)
        choices_scroll = ttk.Scrollbar(choices_box, orient='vertical', command=choices_canvas.yview)
        choices_canvas.configure(yscrollcommand=choices_scroll.set)
        choices_scroll.pack(side='right', fill='y')
        choices_canvas.pack(side='left', fill='both', expand=True)
        choices = ttk.Frame(choices_canvas)
        choices_window = choices_canvas.create_window((0,0),window=choices,anchor='nw')
        choices.bind('<Configure>', lambda _: choices_canvas.configure(scrollregion=choices_canvas.bbox('all')))
        choices_canvas.bind('<Configure>', lambda event: choices_canvas.itemconfigure(choices_window,width=event.width))
        def scroll_choices(event):
            choices_canvas.yview_scroll(-1 if event.delta > 0 else 1,'units')
            return 'break'
        choices_canvas.bind('<MouseWheel>',scroll_choices)
        self.systems, self.system_labels = {}, {}
        for index, (name, label) in enumerate(workflow.LABELS.items()):
            variable = tk.BooleanVar(value=False)
            self.systems[name] = variable
            box = ttk.Checkbutton(choices, text=label, variable=variable, command=self.invalidate)
            box.grid(row=index, column=0, sticky='w', pady=4)
            box.bind('<MouseWheel>',scroll_choices)
            self.inputs.append(box)
            status = tk.StringVar(value='—')
            self.system_labels[name] = status
            status_label = ttk.Label(choices, textvariable=status, style='Muted.TLabel', font=('Microsoft YaHei UI', 8))
            status_label.grid(row=index,column=1,sticky='e',padx=(10,0))
            status_label.bind('<MouseWheel>',scroll_choices)
        right = ttk.Frame(middle)
        right.pack(side='left', fill='both', expand=True)
        tabs = ttk.Notebook(right)
        tabs.pack(fill='both', expand=True)
        overview = ttk.Frame(tabs, padding=12)
        advanced_page = ttk.Frame(tabs)
        advanced_canvas = tk.Canvas(advanced_page, highlightthickness=0)
        advanced_scroll = ttk.Scrollbar(advanced_page, orient='vertical', command=advanced_canvas.yview)
        advanced_canvas.configure(yscrollcommand=advanced_scroll.set)
        advanced_scroll.pack(side='right', fill='y')
        advanced_canvas.pack(side='left', fill='both', expand=True)
        advanced = ttk.Frame(advanced_canvas, padding=12)
        advanced_window = advanced_canvas.create_window((0, 0), window=advanced, anchor='nw')
        advanced.bind('<Configure>', lambda _: advanced_canvas.configure(scrollregion=advanced_canvas.bbox('all')))
        advanced_canvas.bind('<Configure>', lambda event: advanced_canvas.itemconfigure(advanced_window, width=event.width))
        tabs.add(overview, text='准备与结果')
        tabs.add(advanced_page, text='图文、金手指与旧存档')
        self.online = tk.BooleanVar(value=True)
        online_box = ttk.Checkbutton(overview, text='联网匹配中文名称和封面（只下载资料，ROM 留在本地）', variable=self.online, command=self.invalidate)
        online_box.pack(anchor='w')
        self.inputs.append(online_box)
        self.companions = tk.BooleanVar(value=True)
        companion_box = ttk.Checkbutton(overview, text='按需补装 PCE CD、SFC 特殊卡带和 MD PAL 的原版入口',
                                         variable=self.companions, command=self.invalidate)
        companion_box.pack(anchor='w')
        self.inputs.append(companion_box)
        self.import_progress = tk.BooleanVar(value=True)
        progress_box = ttk.Checkbutton(overview, text='迁移卡上已有的普通存档；已有目标进度自动保留', variable=self.import_progress, command=self.invalidate)
        progress_box.pack(anchor='w', pady=(6, 12))
        self.inputs.append(progress_box)
        self.log = tk.Text(overview, wrap='word', height=15, relief='flat', background='#f1f4f3', foreground='#243b36', padx=14, pady=12, state='disabled')
        self.log.pack(fill='both', expand=True)
        self.append('先选择卡目录，再点“识别游戏库”。\n\n缺少封面时生成文字封面；没有中文映射时显示原文件名。\n多个不同存档会让你选择，不会按日期猜测。')
        for row, (label, name, is_file) in enumerate([
            ('核心包目录', 'packages', False), ('自定义中文名 JSON', 'titles', True),
            ('自定义封面目录', 'covers', False), ('GBC BIOS（自备）', 'bios', True),
            ('金手指版本索引', 'cheats', True), ('另一张 Pocket 卡/副本', 'donor', False)]):
            self.path_row(advanced, label, name, row, is_file)
        ttk.Label(advanced, text='金手指只对当前核心已实现且 ROM 版本精确匹配的项目生效。', style='Muted.TLabel', wraplength=610).grid(row=6, column=0, columnspan=3, sticky='w', pady=(10, 8))
        self.raw_system = tk.StringVar(value='不导入模拟器存档')
        ttk.Label(advanced, text='模拟器普通存档').grid(row=7, column=0, sticky='w')
        raw = ttk.Combobox(advanced, textvariable=self.raw_system, values=['不导入模拟器存档', 'GBA', 'GB-GBC'], state='readonly')
        raw.grid(row=7, column=1, columnspan=2, sticky='ew')
        raw.bind('<<ComboboxSelected>>', lambda _: self.invalidate())
        self.inputs.append(raw)
        self.path_row(advanced, '源 ROM 目录', 'donor_roms', 8)
        self.path_row(advanced, '源普通存档目录', 'donor_saves', 9)
        ttk.Label(advanced, text='模拟器导入支持已知 raw .sav/.srm。需要源 ROM 核对版本；即时存档不通用。', style='Muted.TLabel', wraplength=610).grid(row=10, column=0, columnspan=3, sticky='w', pady=8)
        self.skip_invalid = tk.BooleanVar(value=True)
        skip = ttk.Checkbutton(advanced, text='跳过超出容量的 GB/GBC、无效 GBA 文件头；保留原文件并记录', variable=self.skip_invalid, command=self.invalidate)
        skip.grid(row=11, column=0, columnspan=3, sticky='w')
        self.inputs.append(skip)
        self.gba_modes = {}
        for index, name in enumerate(('GBA-MEMORIES', 'GBA-CHEATS'), 12):
            value = tk.BooleanVar(value=False)
            self.gba_modes[name] = value
            option = ttk.Checkbutton(advanced, text='另装 '+workflow.COMPAT_LABELS[name],
                                     variable=value, command=self.invalidate)
            option.grid(row=index, column=0, columnspan=3, sticky='w', pady=3)
            self.inputs.append(option)
        ttk.Label(advanced, text='这两个选项由原作者核心运行，安装后在 GBA 分组使用 Change Core。',
                  style='Muted.TLabel', wraplength=610).grid(row=14, column=0, columnspan=3, sticky='w', pady=8)
        bar = ttk.Frame(frame)
        bar.pack(fill='x')
        self.prepare_button = ttk.Button(bar, text='准备游戏库', style='Accent.TButton', command=self.prepare)
        self.prepare_button.pack(side='left')
        self.install_button = ttk.Button(bar, text='备份并安装', style='Accent.TButton', command=self.install, state='disabled')
        self.install_button.pack(side='left', padx=10)
        self.open_button = ttk.Button(bar, text='查看本次报告', command=self.open_report, state='disabled')
        self.open_button.pack(side='left')
        self.restore_button = ttk.Button(bar, text='从备份恢复菜单', command=self.restore)
        self.restore_button.pack(side='right')
        self.inputs += [self.prepare_button, self.restore_button]
        self.status = tk.StringVar(value='就绪 · 尚未对卡进行写入')
        status_label = ttk.Label(frame, textvariable=self.status, style='Muted.TLabel')
        # Reserve the actions before the expanding content, including on short screens.
        middle.pack_forget()
        bar.pack_forget()
        status_label.pack(side='bottom', anchor='w', pady=(12, 0))
        bar.pack(side='bottom', fill='x')
        middle.pack(fill='both', expand=True, pady=(16, 12))
        for value in self.values.values():
            value.trace_add('write', self.invalidate)
        self.root.after(80, self.poll)

    def path_row(self, parent, label, name, row, is_file=False):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky='w', pady=4, padx=(0, 10))
        entry = ttk.Entry(parent, textvariable=self.values[name])
        entry.grid(row=row, column=1, sticky='ew', pady=4)
        button = ttk.Button(parent, text='选择', width=6, command=lambda: self.browse(name, is_file))
        button.grid(row=row, column=2, padx=(8, 0))
        parent.columnconfigure(1, weight=1)
        self.inputs += [entry, button]

    def browse(self, name, is_file=False):
        path = filedialog.askopenfilename(parent=self.root) if is_file else filedialog.askdirectory(parent=self.root)
        if path:
            self.values[name].set(path)

    def append(self, message):
        self.log.configure(state='normal')
        self.log.insert('end', message+'\n')
        self.log.see('end')
        self.log.configure(state='disabled')

    def invalidate(self, *_):
        if self.engine:
            self.engine.staging = None
        self.report = None
        if hasattr(self, 'install_button'):
            self.install_button.configure(state='disabled')

    def engine_for_inputs(self):
        return workflow.Workflow(self.values['packages'].get(), self.values['work'].get(),
                                 progress=lambda text: self.events.put(('progress', text)))

    def task(self, action, complete, status):
        if self.busy:
            return
        self.busy = True
        self.status.set(status)
        for control in self.inputs:
            control.state(['disabled'])
        self.install_button.state(['disabled'])
        def run():
            try:
                self.events.put(('result', (complete, action())))
            except Exception as exc:
                self.events.put(('error', (str(exc), traceback.format_exc())))
        threading.Thread(target=run, daemon=False).start()

    def poll(self):
        try:
            while True:
                kind, value = self.events.get_nowait()
                if kind == 'progress':
                    self.status.set(value)
                else:
                    self.busy = False
                    for control in self.inputs:
                        control.state(['!disabled'])
                    if kind == 'result':
                        callback, result = value
                        callback(result)
                    else:
                        self.invalidate()
                        self.status.set('本次任务未完成；请查看下面的原因。')
                        explanation = friendly_error(value[0])
                        self.append('需要处理：'+explanation)
                        if self.engine and self.engine.session and self.engine.session.is_dir():
                            try:
                                (self.engine.session/'error.log').write_text(value[1], encoding='utf8')
                            except OSError:
                                self.append('工作目录无法写入错误日志。')
                            else:
                                self.open_button.state(['!disabled'])
                        messagebox.showerror('任务未完成', explanation, parent=self.root)
        except queue.Empty:
            pass
        finally:
            self.root.after(80, self.poll)

    def detect(self):
        def done(cards):
            if not cards:
                self.append('没有找到带 Pocket 标记的卡。也可以用“选择”指定卡的本地副本。')
            elif len(cards) == 1:
                self.values['card'].set(cards[0]['root'])
                self.inspect()
            else:
                self.append('找到多个候选，请选择：\n'+'\n'.join(c['root']+'  卷 '+c['device'] for c in cards))
        self.task(workflow.detect_cards, done, '正在查找 Pocket 卡…')

    def inspect(self):
        self.invalidate()
        self.engine = self.engine_for_inputs()
        card = self.values['card'].get()
        def done(result):
            ident = result['identity']
            location = '卷根目录' if Path(ident['root']) == Path(Path(ident['root']).anchor) else '目录/本地副本'
            self.identity.set(f'{location}   ·   卷编号 {ident["device"]}   ·   Pocket 标记已核对')
            for name, value in self.systems.items():
                count = result['systems'].get(name, 0)
                ready = result['packages'].get(name, False)
                value.set(bool(count and ready))
                state = '核心未通过核对' if name in result.get('package_errors', {}) else '缺核心包'
                self.system_labels[name].set(state if count and not ready else f'{count} 项')
            self.append('已识别 '+str(sum(result['systems'].values()))+' 个游戏入口。请选择机种，然后准备。')
            scan = result['compatibility']
            if scan['pcecd'] or scan['special_sfc'] or scan['unsupported_discs']:
                self.append(f'兼容入口可处理 {len(scan["pcecd"])} 张 CUE/BIN 光盘和 '
                            f'{len(scan["special_sfc"])} 部 SFC 特殊卡带。')
            if scan['pal_md']:
                self.append(f'有 {len(scan["pal_md"])} 部 PAL 区 MD 卡带可走原版入口。')
            self.status.set('识别完成 · 尚未写入')
        self.task(lambda: self.engine.inspect(card), done, '正在识别游戏库…')

    def prepare(self):
        self.invalidate()
        self.engine = self.engine_for_inputs()
        values = {k: v.get().strip() for k, v in self.values.items()}
        systems = [s for s, v in self.systems.items() if v.get()]
        migration = {'same_card': self.import_progress.get(), 'sources': []}
        if values['donor']:
            migration['sources'].append({'root': values['donor'], 'format': 'pocket-native'})
        if self.raw_system.get() != '不导入模拟器存档':
            if not values['donor_roms'] or not values['donor_saves']:
                messagebox.showinfo('需要源目录', '请选择模拟器的源 ROM 目录和普通存档目录。', parent=self.root)
                return
            try:
                common = Path(os.path.commonpath([values['donor_roms'], values['donor_saves']])).resolve()
                migration['sources'].append({'root': str(common), 'format': 'raw-handheld', 'system': self.raw_system.get(),
                    'roms': Path(values['donor_roms']).resolve().relative_to(common).as_posix(),
                    'saves': Path(values['donor_saves']).resolve().relative_to(common).as_posix()})
            except ValueError:
                messagebox.showinfo('源目录不匹配', '源 ROM 和存档需要位于同一个磁盘上的两个目录。', parent=self.root)
                return
        options = {k: values[k] or None for k in ('titles', 'covers', 'bios', 'cheats')}
        options.update(online=self.online.get(), skip_invalid=self.skip_invalid.get(), save_import=migration,
                       companions=self.companions.get(),
                       gba_modes=[name for name, value in self.gba_modes.items() if value.get()])
        self.task(lambda: self.engine.prepare(values['card'], systems, **options), self.prepared, '正在准备游戏库…')

    def prepared(self, result):
        self.open_button.state(['!disabled'])
        if result['status'] == 'save_conflict':
            self.status.set('存档需要选择 · 尚未写入')
            self.resolve_dialog(result['report'])
            return
        self.report = result
        labels = workflow.LABELS | workflow.COMPAT_LABELS
        compat = result['compatibility']
        for system, status in compat['entries'].items():
            self.append(labels[system]+' · '+status)
        invalid_sfc = compat['scan']['invalid_sfc']
        invalid_md = compat['scan']['invalid_md']
        discs = compat['scan']['unsupported_discs']
        if invalid_sfc or invalid_md:
            self.append(f'有 {len(invalid_sfc)} 个 SFC 和 {len(invalid_md)} 个 MD 文件的卡带头无法识别。详情见本次报告。')
        if discs:
            self.append(f'有 {len(discs)} 张光盘无法加入原版入口。首项原因 · {discs[0]["reason"]}。详情见本次报告。')
        if result['status'] == 'no_install':
            self.status.set('没有待安装项目 · 查看本次报告')
            if not compat['entries'] and not invalid_sfc and not invalid_md and not discs:
                self.append('请先识别游戏库，再勾选要准备的机种。')
            return
        meta = result['metadata']
        migration = result['save_import'] or {}
        self.append('\n准备完成：'+', '.join(labels[n] for n in result['systems'])+
            f'\n中文名匹配 {meta["matched_titles"]}；封面匹配 {meta["matched_covers"]}；文字封面 {len(meta["missing_covers"])}。'+
            f'\n迁移普通存档 {migration.get("imports", 0) + migration.get("native_instance_imports", 0)}；保留已有进度 {migration.get("existing_preserved", 0)}。'+
            f'\n计划写入 {result["writes"]} 个文件，{result["bytes"]/1024**2:.1f} MB。'+
            '\n备份位置：'+str(self.engine.work/'backups'/self.engine.session.name))
        excluded = sum(v['excluded'] for v in result['menus']['systems'].values())
        cheat_matches = sum(v.get('cheat_matched_versions', 0) for v in result['menus']['systems'].values())
        if cheat_matches:
            self.append(f'已匹配 {cheat_matches} 个游戏版本的金手指。具体效果见本次报告。')
        save_warnings = migration.get('existing_save_warnings', migration.get('existing_rtc_warnings', 0))
        if save_warnings:
            self.append(f'{save_warnings} 份已有存档包含格式或时钟提示，原文件已保留。详见存档报告。')
        if excluded or meta['errors']:
            self.append(f'需查看报告：未纳入 {excluded} 个入口；资料源问题 {len(meta["errors"])} 项。')
        if meta['offline_cache_misses']:
            self.append('离线缓存不全，未匹配的项目保留文件名和文字封面。联网准备时可以补齐。')
        need, free = result['card_required_bytes'], result['card_free_bytes']
        self.append(f'卡上剩余 {free/1024**2:.1f} MB，本次写入及恢复预计需预留 {need/1024**2:.1f} MB。')
        if free < need:
            self.status.set('卡空间不足 · 减少机种后重新准备')
            return
        self.install_button.state(['!disabled'])
        self.status.set('准备完成 · 点击“备份并安装”后才会更新卡')

    def resolve_dialog(self, report):
        window = tk.Toplevel(self.root)
        window.title('选择要迁移的普通存档')
        window.geometry('820x520')
        window.transient(self.root)
        window.grab_set()
        outer = ttk.Frame(window, padding=18)
        outer.pack(fill='both', expand=True)
        ttk.Label(outer, text='发现不同进度或不兼容格式。请选择来源；原文件都会保留。', wraplength=760).pack(anchor='w')
        canvas = tk.Canvas(outer, highlightthickness=0)
        scroll = ttk.Scrollbar(outer, orient='vertical', command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        canvas.pack(fill='both', expand=True, pady=12)
        entries = ttk.Frame(canvas)
        canvas.create_window(0, 0, window=entries, anchor='nw', width=740)
        entries.bind('<Configure>', lambda _: canvas.configure(scrollregion=canvas.bbox('all')))
        selections = []
        for row in report['games']:
            if row['status'] != 'conflict':
                continue
            ttk.Label(entries, text=row['rom']['path'], wraplength=720).pack(anchor='w', pady=(8, 3))
            choices = [('本次不迁移，保留原文件', 'skip')]+[(c['root']+'/'+c['save']['path']+' · '+c['save']['sha256'][:8], c['id']) for c in row['candidates']]
            value = tk.StringVar(value='请选择')
            box = ttk.Combobox(entries, textvariable=value, values=[c[0] for c in choices], state='readonly', width=80)
            box.pack(fill='x', pady=(0, 5))
            for error in row['errors']:
                ttk.Label(entries, text=error, wraplength=720, style='Muted.TLabel').pack(anchor='w')
            selections.append((row['path'], value, dict(choices)))
        def finish():
            if any(v.get() not in options for _, v, options in selections):
                messagebox.showinfo('还有未选择的项目', '请逐项选择，或关闭窗口稍后处理。', parent=window)
                return
            choices = {path: options[v.get()] for path, v, options in selections}
            window.destroy()
            self.task(lambda: self.engine.resolve_saves(choices), self.prepared, '正在重新核对选定存档…')
        ttk.Button(outer, text='按这些选择继续准备', command=finish).pack(anchor='e')

    def install(self):
        def done(result):
            self.last_backup = result['backup']
            self.append('\n安装完成，文件回读校验通过。备份：'+result['backup']+'\n可以安全弹出卡，再按验收清单上机测试。')
            self.status.set('文件安装完成 · 实机体验待验收')
        self.task(self.engine.install, done, '正在备份并安装，请保持卡连接…')

    def restore(self):
        backup = filedialog.askdirectory(parent=self.root, title='选择包含 delivery-receipt.json 的备份目录')
        if not backup:
            return
        card = self.values['card'].get()
        try:
            preview = delivery.rollback(card, backup)
        except (OSError, ValueError, KeyError) as exc:
            messagebox.showerror('备份不能用于当前卡', str(exc), parent=self.root)
            return
        if not messagebox.askokcancel('恢复菜单', f'将恢复 {preview["menu_files_restored"]} 个菜单文件。已有普通存档会保留。', parent=self.root):
            return
        engine = self.engine_for_inputs()
        def done(result):
            self.append('菜单已恢复，当前普通存档已保留。')
            self.status.set('菜单恢复完成 · 当前普通存档已保留')
        self.task(lambda: engine.restore(card, backup), done, '正在恢复菜单…')

    def open_report(self):
        if self.engine and self.engine.session:
            os.startfile(str(self.engine.session)) if os.name == 'nt' else self.append(str(self.engine.session))

    def close(self):
        if self.busy:
            messagebox.showinfo('任务正在进行', '请等当前任务完成后关闭，避免中断备份或写入。', parent=self.root)
        else:
            self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packages', type=Path)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--job', type=Path, help='Run an explicit JSON prepare/apply/restore job without opening a window')
    args = parser.parse_args()
    if args.job:
        job = delivery.read(args.job)
        output = Path(job['result']).resolve()
        card = Path(job['card']).resolve()
        delivery.separate(card, output)
        if output.exists():
            raise ValueError('Use a new result file')
        try:
            if job['action'] == 'prepare':
                engine = workflow.Workflow(job['packages'], job['work'])
                result = engine.prepare(card, job['systems'], **job.get('options', {}))
            elif job['action'] == 'apply':
                result = delivery.apply(card, job['staging'], job['backup'])
            elif job['action'] == 'restore':
                result = delivery.rollback(card, job['backup'], execute=True)
            else:
                raise ValueError('Unknown desktop job action')
            delivery.write(output, result)
        except Exception as exc:
            delivery.write(output, {'status': 'failed', 'error': str(exc), 'traceback': traceback.format_exc()})
            raise SystemExit(2)
        return
    root = tk.Tk()
    Assistant(root, args.packages, args.work)
    root.mainloop()


if __name__ == '__main__':
    main()
