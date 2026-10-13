#!/usr/bin/env python3
"""Create a provenance manifest for oracle bundles before they enter training."""
from __future__ import annotations
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable
import argparse, json

def manifest(paths: Iterable[Path | str], *, strict_rights: bool = False) -> Dict[str, Any]:
    rows=[]; warnings=[]
    for raw_path in paths:
        path=Path(raw_path); data=json.loads(path.read_text(encoding='utf-8')); meta=dict(data.get('metadata') or {})
        digest=sha256(path.read_bytes()).hexdigest()
        fixture=bool(meta.get('fixture'))
        rights=meta.get('license') or meta.get('rights_basis')
        if not fixture and not rights:
            msg=f"{path.name}: missing license/rights_basis"
            if strict_rights: raise ValueError(msg)
            warnings.append(msg)
        rows.append({
            'talk_id':data.get('talk_id') or path.stem,'path':str(path),'sha256':digest,'fixture':fixture,
            'source_uri':meta.get('source_uri'),'license':meta.get('license'),'rights_basis':meta.get('rights_basis'),
            'domain':meta.get('domain'),'language':meta.get('language'),
            'editors':[{'name':e.get('name'),'shape':e.get('shape'),'version':e.get('version')} for e in data.get('editors') or []],
        })
    return {'version':10,'schema':'live_presenter.oracle_manifest.v1','bundles':rows,'warnings':warnings}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('bundles',nargs='+');ap.add_argument('--out',required=True);ap.add_argument('--strict-rights',action='store_true');args=ap.parse_args()
    m=manifest(args.bundles,strict_rights=args.strict_rights);p=Path(args.out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(m,indent=2)+'\n',encoding='utf-8');print(json.dumps({'bundles':len(m['bundles']),'warnings':m['warnings']},indent=2))
if __name__=='__main__':main()
