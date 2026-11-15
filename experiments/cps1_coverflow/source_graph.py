# SPDX-License-Identifier: MIT
"""Collect the native Quartus source closure without copying game ROMs."""
import hashlib,re,shutil
from pathlib import Path

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def collect(root,platform):
    root=Path(root).resolve();project=root/'cores'/platform/'pocket'
    pending=[project/f'jt{platform}.qsf',project/f'jt{platform}.qpf']
    files=set();search=[project,project.parent/'hdl',root/'modules/jtframe/hdl/inc']
    def add(path,required=True):
        path=path.resolve()
        if not path.is_relative_to(root):raise ValueError('Source leaves root: '+str(path))
        if not path.is_file():
            if required:raise ValueError('Missing source dependency: '+str(path))
            return
        if path not in files:pending.append(path)
    while pending:
        p=pending.pop()
        if p in files:continue
        if not p.is_file():raise ValueError('Missing Quartus input: '+str(p))
        files.add(p)
        if p.suffix not in {'.qsf','.qip','.v','.vh','.sv','.svh','.vhd','.sdc','.tcl'}:continue
        text=p.read_text(encoding='utf8',errors='replace')
        if p.suffix in {'.qsf','.qip'}:
            for m in re.finditer(r'-name\s+(\w+)\s+(.+)',text):
                kind,value=m.groups()
                if kind not in {'VERILOG_FILE','SYSTEMVERILOG_FILE','VHDL_FILE','QIP_FILE','SDC_FILE','MISC_FILE','HEX_FILE','SEARCH_PATH'}:continue
                if value.startswith('[file join $::quartus(qip_path) '):
                    parts=re.findall(r'"([^"]+)"',value)
                    if len(parts)!=1:raise ValueError('Unexpected QIP expression: '+value)
                    target=p.parent/parts[0]
                elif value.startswith('"'):
                    target=project/value.split('"')[1]
                elif not any(c in value.split()[0] for c in '$[]'):
                    target=project/value.split()[0]
                else:raise ValueError('Unrecognized native QIP expression: '+value)
                if kind=='SEARCH_PATH':search.append(target.resolve())
                # Quartus MISC_FILE is an IP-editor preview, not synthesis.
                # The upstream archive omits several .ppf/.cmp previews.
                else:add(target,required=kind!='MISC_FILE')
        for inc in re.findall(r'`include\s+"([^"]+)"',text):
            matches=[d/inc for d in [p.parent]+search if (d/inc).is_file()]
            if not matches:raise ValueError('Missing HDL include '+inc+' from '+str(p))
            add(matches[0])
        for ref in re.findall(r'"([^"\n]+\.(?:hex|mif))"',text,re.I):
            for d in [project,p.parent]+search:
                if (d/ref).is_file():add(d/ref);break
        if p.suffix=='.sdc':
            for ref in re.findall(r'(?:read_sdc|source)\s+"([^"\n]+)"',text):
                choices=[d/ref for d in [project,p.parent] if (d/ref).is_file()]
                if choices:add(choices[0])
    # LUTs and include files in participating source directories are source
    # dependencies even when selected through a parameter or macro.
    for directory in {p.parent for p in files}|{project,root/'modules/jtframe/hdl/inc'}:
        for suffix in ('*.hex','*.mif','*.vh','*.svh'):
            files.update(p.resolve() for p in directory.glob(suffix) if p.is_file())
    for p in list(files):
        for parent in [p.parent,*p.parents]:
            if not parent.is_relative_to(root):break
            for name in ('LICENSE','LICENSE.txt','COPYING'):
                if (parent/name).is_file():files.add(parent/name)
    for p in (root/'LICENSE',root/'README.md'):
        if p.is_file():files.add(p)
    return sorted(files)

def copy(root,platform,out):
    root,out=Path(root).resolve(),Path(out).resolve()
    if out.exists():raise ValueError('Source output must be new')
    files=collect(root,platform)
    for p in files:
        q=out/p.relative_to(root);q.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,q)
    return {p.relative_to(root).as_posix():sha(p) for p in files}
