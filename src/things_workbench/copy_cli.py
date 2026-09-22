"""Explicit opt-in copy experiments, separate from read-only --db commands."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from . import copies, native_runtime, wording


def main(argv):
    p=argparse.ArgumentParser(prog='things-workbench',description='Experimental private copy-only tooling. Bounded wording/history subset; no live/cloud support.')
    commands=p.add_subparsers(dest='family',required=True)
    c=commands.add_parser('copies',description='Import a declared stable private detached copy; never discover live data.')
    sub=c.add_subparsers(dest='operation',required=True)
    imp=sub.add_parser('import'); imp.add_argument('--snapshot',required=True); imp.add_argument('--workspace',required=True); imp.add_argument('--declare',required=True,choices=['detached-stable-resolved'])
    n=commands.add_parser('native',description='Explicit native copy helper build; nothing builds on import/help.')
    sub=n.add_subparsers(dest='operation',required=True)
    b=sub.add_parser('build'); b.add_argument('--app',required=True); b.add_argument('--output',required=True)
    w=commands.add_parser('wording',description='Copy-only prepare, exact escaped preview and digest-approved apply-copy. Only the documented bounded history subset is supported.')
    sub=w.add_subparsers(dest='operation',required=True)
    prep=sub.add_parser('prepare'); prep.add_argument('--copy',required=True); prep.add_argument('--plan',required=True); prep.add_argument('--packet',required=True); prep.add_argument('--runtime',required=True)
    prev=sub.add_parser('preview'); prev.add_argument('--packet',required=True)
    apply=sub.add_parser('apply-copy'); apply.add_argument('--packet',required=True); apply.add_argument('--approve',required=True)
    args=p.parse_args(argv)
    try:
        if args.family=='copies': result={'copy':str(copies.import_copy(args.snapshot,args.workspace,declaration=args.declare)),'supplier_declaration_only':True}
        elif args.family=='native': result={'runtime':str(native_runtime.build(args.app,args.output))}
        elif args.operation=='prepare':
            plan=wording.parse_plan(copies.read_bytes(args.plan))
            result={'packet':str(wording.prepare(args.copy,plan,args.packet,args.runtime))}
        elif args.operation=='preview': result=wording.preview(args.packet)
        else: result={'output_copy':str(wording.apply_copy(args.packet,args.approve)),'live_published':False}
    except copies.CopyError as exc:
        print('copy refused: '+str(exc),file=sys.stderr); return 2
    except (OSError,ValueError,KeyError,TypeError,sqlite3.Error):
        print('copy refused: invalid or unavailable private artifact',file=sys.stderr); return 2
    print(json.dumps(result,ensure_ascii=True,sort_keys=True,indent=2,allow_nan=False))
    return 0
