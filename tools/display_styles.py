#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Declare supported Pocket display modes without selecting an OS filter."""
import copy

# None (0x00) is an OS choice, never a JSON display_modes entry. Grayscale
# modes require a 00B8 reply plus grayscale RGB; these candidates lack that
# path. A color LCD mode remains available for GB in the shared GB/GBC core.
MODES={'gbc':['0x31','0x32','0x30','0x40','0x10'],
       'gba':['0x41','0x42','0x30','0x40','0x10'],
       'nes':['0x10'],'gg':['0x51','0x52','0x30','0x40','0x10'],
       'sms':['0x10'],'sg1000':['0x10']}


def configure(value,platform):
    result=copy.deepcopy(value);video=result['video']
    if video.get('magic')!='APF_VER_1' or not 1<=len(video['scaler_modes'])<=8:raise ValueError('APF video/scaler definition required')
    video['display_modes']=[{'id':mode} for mode in MODES[platform]]
    video.setdefault('defaults',{})['sharpness']=3
    return result
