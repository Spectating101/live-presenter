#!/usr/bin/env python3
"""Assemble a real oracle bundle from transcript + editor output files."""
from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, List, Mapping, Sequence, Tuple
import argparse, json, re
from oracle_dataset_v10 import SUPPORTED_SHAPES, load_bundle

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

def load_editor_rows(path:Path|str)->List[Dict[str,Any]]:
    raw=json.loads(Path(path).read_text(encoding='utf-8'))
    if isinstance(raw,list): return raw
    for key in ('events','broll','edits','items'):
        if isinstance(raw.get(key),list): return raw[key]
    raise ValueError(f"cannot find editor event array in {path}")

def assemble_bundle(*,talk_id:str,transcript:Sequence[Mapping[str,Any]],editors:Sequence[Tuple[str,str,Sequence[Mapping[str,Any]]]],context:Mapping[str,Any]|None=None,metadata:Mapping[str,Any]|None=None)->Dict[str,Any]:
    if not talk_id.strip(): raise ValueError('talk_id required')
    editor_rows=[]
    for name,shape,events in editors:
        if shape not in SUPPORTED_SHAPES: raise ValueError(f'unsupported editor shape: {shape}')
        if not name.strip(): raise ValueError('editor name required')
        editor_rows.append({'name':name,'shape':shape,'events':[dict(x) for x in events]})
    if not editor_rows: raise ValueError('at least one editor required')
    return {'talk_id':talk_id.strip(),'context':dict(context or {}),'metadata':dict(metadata or {}),'transcript':[dict(x) for x in transcript],'editors':editor_rows}

def _parse_editor_spec(spec:str)->Tuple[str,str,Path]:
    try:name,shape,path=spec.split(':',2)
    except ValueError: raise ValueError("editor spec must be name:shape:path") from None
    return name,shape,Path(path)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--talk-id',required=True); ap.add_argument('--transcript',required=True)
    ap.add_argument('--editor',action='append',default=[],help='name:shape:path; repeat per editor'); ap.add_argument('--out',required=True)
    ap.add_argument('--source-uri'); ap.add_argument('--license'); ap.add_argument('--rights-basis'); ap.add_argument('--domain'); ap.add_argument('--language')
    for x in ('has-dataset','has-images','has-sources','graph-ready','has-map-data','has-timeline-data'): ap.add_argument('--'+x,action='store_true')
    args=ap.parse_args(); editors=[]
    for spec in args.editor:
        name,shape,path=_parse_editor_spec(spec); editors.append((name,shape,load_editor_rows(path)))
    metadata={k:v for k,v in {'source_uri':args.source_uri,'license':args.license,'rights_basis':args.rights_basis,'domain':args.domain,'language':args.language}.items() if v}
    context={k:bool(getattr(args,k)) for k in ('has_dataset','has_images','has_sources','graph_ready','has_map_data','has_timeline_data')}
    bundle=assemble_bundle(talk_id=args.talk_id,transcript=load_transcript(args.transcript),editors=editors,context=context,metadata=metadata)
    out=Path(args.out); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(bundle,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    validated=load_bundle(out)
    print(json.dumps({'talk_id':validated.talk_id,'transcript_segments':len(validated.transcript),'editors':validated.editor_names,'context':validated.context,'out':str(out)},indent=2))
if __name__=='__main__':main()
