# SPDX-License-Identifier: MIT
"""Resolve native CPS Pocket instances without changing ROM or save bytes."""
import hashlib,importlib.util,json,re,struct,sys
from pathlib import Path,PurePosixPath
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT/'tools') not in sys.path:sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('cps_family_install',ROOT/'tools/install.py')
fs=importlib.util.module_from_spec(spec);spec.loader.exec_module(fs)
PROFILES={'jtcps1':'cp1lab','jtcps15':'c15lab'}
CONTROLS={0xf9000000:'core_mode',0xfa000000:'dip_switches',0xfc000000:'button_map'}

def save_id(rom_digest,core_mode,button_map,dip_switches):
    return hashlib.sha256(bytes.fromhex(rom_digest)+struct.pack('<III',core_mode,button_map,dip_switches)).hexdigest()[:20]

def uint(value):
    if isinstance(value,str) and re.fullmatch(r'0x[0-9a-fA-F]+',value):value=int(value,16)
    if type(value) is not int or not 0<=value<=0xffffffff:raise ValueError('Expected unsigned 32-bit instance value')
    return value

def relative(value):
    if not isinstance(value,str) or len(value.encode('utf8'))>255:raise ValueError('Invalid instance path')
    if value and any(p in ('','.','..') for p in value.rstrip('/').split('/')):raise ValueError('Instance path is not relative')
    if '\\' in value or ':' in value:raise ValueError('Invalid APF path separator')
    return value.rstrip('/')

def instance_files(card,platform):
    if platform not in PROFILES:raise ValueError('Unsupported native CPS platform')
    for rel in (f'Assets/{platform}/common',f'Assets/{platform}/jotego.{platform}'):
        for path in sorted(fs.safe_path(card,rel).rglob('*.json')):
            if path.is_file():yield path

def plan(card,instance_path,platform):
    card=Path(card).resolve();namespace=PROFILES[platform]
    assets=PurePosixPath('Assets')/platform/'common';specific=assets.with_name('jotego.'+platform)
    rel=PurePosixPath(relative(instance_path))
    if not any(rel.is_relative_to(p) for p in (assets,specific)) or rel.suffix.lower()!='.json':raise ValueError('Expected native Pocket instance path')
    path=fs.safe_path(card,rel.as_posix());instance=json.loads(path.read_text(encoding='utf-8-sig'))['instance']
    if not isinstance(instance,dict) or instance.get('magic')!='APF_VER_1':raise ValueError('Invalid APF instance version')
    if set(instance)-{'magic','data_path','core_select','variant_select','data_slots','memory_writes'}:raise ValueError('Unsupported instance options')
    for key in ('core_select','variant_select'):
        selection=instance.get(key,{'id':0,'select':False})
        if uint(selection['id'])!=0 or selection['select'] is not False:raise ValueError('Only native default bitstream is supported')
    slots={};md5=None
    for row in instance['data_slots']:
        slot=uint(row['id']);name=relative(row['filename'])
        if slot in slots or slot not in (1,2):raise ValueError('Unsupported or duplicate native data slot')
        if PurePosixPath(name).suffix.lower()!=('.rom' if slot==1 else '.sav'):raise ValueError('Unexpected native file extension')
        slots[slot]=name
        if slot==1 and 'md5' in row:
            md5=row['md5']
            if not isinstance(md5,str) or not re.fullmatch('[0-9a-fA-F]{32}',md5):raise ValueError('Invalid native ROM checksum')
    if set(slots)!={1,2}:raise ValueError('Native instance needs ROM and NVRAM filenames')
    settings={}
    for row in instance.get('memory_writes',[]):
        addr,value=uint(row['address']),uint(row['data'])
        if addr not in CONTROLS or CONTROLS[addr] in settings:raise ValueError('Unsupported or duplicate control register')
        settings[CONTROLS[addr]]=value
    settings.setdefault('button_map',0x543210);settings.setdefault('dip_switches',0xffffffff)
    if 'core_mode' not in settings or settings['button_map']>0xffffff:raise ValueError('Native mode and 24-bit button map are required')
    folder=(rel.parent if rel.is_relative_to(assets) else assets)/relative(instance.get('data_path',''))
    rom=fs.safe_path(card,(folder/slots[1]).as_posix())
    if not rom.is_file():raise ValueError('Native instance ROM is missing')
    size=rom.stat().st_size
    if size<64 or size>64*1024**2 or size%4:raise ValueError('Native CPS ROM size is unsupported')
    digest=hashlib.sha256();check=hashlib.md5()
    with rom.open('rb') as f:
        for block in iter(lambda:f.read(1024**2),b''):digest.update(block);check.update(block)
    if md5 and check.hexdigest()!=md5.lower():raise ValueError('Native ROM checksum differs')
    digest=digest.hexdigest();tag=save_id(digest,**settings)
    old_save=PurePosixPath('Saves')/platform/'common'/(folder/slots[2]).relative_to(assets)
    fs.safe_path(card,old_save.as_posix())
    return {'instance':rel.as_posix(),'instance_sha256':fs.sha(path),'title':path.stem,
        'rom':{'slot':1,'path':rom.relative_to(card).as_posix(),'bytes':size,'sha256':digest},
        'nvram':{'slot':2,'bytes':128,'instance_filename':slots[2],'original_path':old_save.as_posix(),
                 'candidate_path':f'Saves/{namespace}/common/{tag}.sav'},**settings}

def available_instances(card,platform):
    card=Path(card).resolve()
    for path in instance_files(card,platform):
        rel=path.relative_to(card).as_posix()
        try:plan(card,rel,platform)
        except (ValueError,KeyError,TypeError,OSError):continue
        yield rel
