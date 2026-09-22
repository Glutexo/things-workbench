"""Explicit private rehearsal commands. True-live is unconditionally disabled."""
import argparse
import json
import sqlite3
import sys
from . import publication as p
from .copies import CopyError


def main(argv):
    parser = argparse.ArgumentParser(prog='things-workbench publication', description='Private DELETE-mode transactional rehearsal; no live/cloud support.')
    sub = parser.add_subparsers(dest='operation', required=True)
    create = sub.add_parser('create-target')
    create.add_argument('--completed-packet', required=True); create.add_argument('--new-root', required=True)
    prepare = sub.add_parser('prepare')
    prepare.add_argument('--completed-packet', required=True); prepare.add_argument('--target-root', required=True); prepare.add_argument('--name', required=True)
    for name in ('preview', 'status', 'rehearse', 'publish-live', 'recovery-preview', 'restore-copy'):
        command = sub.add_parser(name); command.add_argument('--run', required=True)
        if name in ('rehearse', 'publish-live'): command.add_argument('--approve', required=True)
        if name == 'recovery-preview':
            command.add_argument('--name', required=True)
            command.add_argument('--authorize-owned-recovery', action='store_true', required=True)
        if name == 'restore-copy': command.add_argument('--new-root', required=True)
    command = sub.add_parser('reconcile')
    command.add_argument('--assessment', required=True); command.add_argument('--approve', required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'publish-live': p.publish_live()
        elif args.operation == 'create-target': result = {'target_root': str(p.create_target(args.completed_packet, args.new_root))}
        elif args.operation == 'prepare': result = {'run': str(p.prepare(args.completed_packet, args.target_root, args.name))}
        elif args.operation == 'preview': result = p.preview(args.run)
        elif args.operation == 'status': result = p.status(args.run)
        elif args.operation == 'rehearse': result = p.rehearse(args.run, approval=args.approve)
        elif args.operation == 'recovery-preview': result = p.recovery_preview(args.run, args.name, authorize_owned_recovery=args.authorize_owned_recovery)
        elif args.operation == 'reconcile': result = p.reconcile(args.assessment, approval=args.approve)
        else: result = {'recovery_copy': str(p.restore_copy(args.run, args.new_root))}
    except CopyError as exc:
        print('publication refused: '+str(exc), file=sys.stderr); return 2
    except (OSError, ValueError, KeyError, TypeError, sqlite3.Error):
        print('publication refused: invalid or unavailable private evidence; retain quarantine', file=sys.stderr); return 2
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 0
