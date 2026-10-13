#!/usr/bin/env python3
"""Transcript readers (SRT/VTT/JSON) with no heavy dependencies."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List
import json, re

def _seconds(ts: str) -> float:
    m=re.fullmatch(r"\s*(?:(\d+):)?(\d{2}):(\d{2})[,.](\d{3})\s*",ts)
    if not m: raise ValueError(f"invalid timestamp: {ts}")
    h=int(m.group(1) or 0); minute=int(m.group(2)); sec=int(m.group(3)); ms=int(m.group(4))
    return h*3600+minute*60+sec+ms/1000

def parse_srt(path:Path|str)->List[Dict[str,Any]]:
    text=Path(path).read_text(encoding='utf-8-sig').replace('\r\n','\n'); blocks=re.split(r"\n\s*\n",text.strip()) if text.strip() else []; out=[]
    for block in blocks:
        lines=[x.rstrip() for x in block.splitlines() if x.strip()]
        if not lines: continue
        timing_idx=next((i for i,x in enumerate(lines) if '-->' in x),None)
        if timing_idx is None: continue
        a,b=[x.strip() for x in lines[timing_idx].split('-->',1)]; b=b.split()[0]
        out.append({'start':_seconds(a),'end':_seconds(b),'text':' '.join(lines[timing_idx+1:]).strip()})
    return out

def load_transcript(path:Path|str)->List[Dict[str,Any]]:
    path=Path(path)
    if path.suffix.lower() in {'.srt','.vtt'}: return parse_srt(path)
    raw=json.loads(path.read_text(encoding='utf-8'))
    if isinstance(raw,list): return raw
    return list(raw.get('transcript') or raw.get('segments') or [])
