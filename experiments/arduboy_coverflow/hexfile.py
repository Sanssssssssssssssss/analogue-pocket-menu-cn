# SPDX-License-Identifier: MIT
"""Validate files against the pinned upstream Arduboy Intel HEX parser."""
def validate(raw):
    if not 12<=len(raw)<=262144:raise ValueError('HEX file must be 12–262144 bytes')
    try:text=raw.decode('ascii')
    except UnicodeDecodeError:raise ValueError('HEX file is not ASCII')
    eof=False;image={}
    for number,line in enumerate(text.splitlines(),1):
        if not line:continue
        if eof:raise ValueError(f'Record after EOF at line {number}')
        if not line.startswith(':') or len(line)%2!=1 or any(c not in '0123456789abcdefABCDEF' for c in line[1:]):
            raise ValueError(f'Invalid HEX record at line {number}')
        data=bytes.fromhex(line[1:])
        if len(data)<5 or len(data)!=data[0]+5 or sum(data)&255:raise ValueError(f'HEX length/checksum at line {number}')
        size=data[0];address=int.from_bytes(data[1:3],'big');kind=data[3]
        if kind==1:
            if size or address:raise ValueError('Invalid EOF record')
            eof=True;continue
        if kind!=0:raise ValueError('Pinned native parser supports data/EOF records only; extended address/FX files are unsupported')
        if not size or address+size>32768:raise ValueError('Program exceeds the native 32KiB memory or contains an empty data record')
        for i,value in enumerate(data[4:-1],address):
            if i in image:raise ValueError('Overlapping program records')
            image[i]=value
    if not eof or len(image)<2 or 0 not in image or 1 not in image:raise ValueError('Missing EOF or reset-vector bytes')
    return {'program_bytes':len(image),'program_end':max(image)+1,'image':image}
