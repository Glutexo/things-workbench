"""Read-only command line interface; no implicit database discovery."""
import argparse
import json
import math
import sys

from . import WorkbenchError, doctor, inspect_schema, list_tasks, show_task


SCHEMA_WARNING = 'Review before sharing: schema DDL and defaults may contain private literals.'


def _json_value(value):
    """Losslessly tag SQLite storage classes JSON cannot represent directly."""
    if isinstance(value, bytes):
        return {'sqlite_blob_hex': value.hex()}
    if isinstance(value, float) and not math.isfinite(value):
        return {'sqlite_real': 'Infinity' if value > 0 else '-Infinity'}
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value


def main(argv=None):
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list and args_list[0] == 'publication':
        from .publication_cli import main as publication_main
        return publication_main(args_list[1:])
    if args_list and args_list[0] in ('copies', 'wording', 'native'):
        from .copy_cli import main as copy_main
        return copy_main(args_list)
    parser = argparse.ArgumentParser(prog='things-workbench', description='Read-only SQLite inspection; no writes, repair or sync.')
    parser.add_argument('--db', required=True, help='Explicit existing SQLite database file (no discovery).')
    parser.add_argument('--timeout', type=float, default=5.0, help='Cooperative inspection time budget, 0 < seconds <= 60 (default: 5).')
    commands = parser.add_subparsers(dest='command', required=True)
    schema = commands.add_parser('schema', help='Export structure only; review DDL/defaults before sharing.')
    schema.add_argument('--json', action='store_true', help='Machine-readable JSON to stdout.')
    diagnostic = commands.add_parser('doctor', help='Inspect readability, not sync safety; no repairs.')
    diagnostic.add_argument('--json', action='store_true')
    tasks = commands.add_parser('tasks', help='Read raw allowlisted fields; no enum/date interpretation.')
    task_commands = tasks.add_subparsers(dest='task_command', required=True)
    listing = task_commands.add_parser('list', help='List raw TMTask rows, including all types/statuses.')
    listing.add_argument('--limit', type=int, default=50, help='1..500, default 50.')
    listing.add_argument('--offset', type=int, default=0, help='0..100000, default 0; pages are independent snapshots.')
    listing.add_argument('--json', action='store_true')
    showing = task_commands.add_parser('show', help='Look up an exact ID; exit 3 if absent.')
    showing.add_argument('id', help='Exactly 22 ASCII alphanumeric characters; never normalized.')
    showing.add_argument('--json', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'tasks':
            if args.task_command == 'list':
                result = list_tasks(args.db, limit=args.limit, offset=args.offset, timeout=args.timeout)
            else:
                result = show_task(args.db, args.id, timeout=args.timeout)
        else:
            operation = inspect_schema if args.command == 'schema' else doctor
            result = operation(args.db, timeout=args.timeout)
    except WorkbenchError as error:
        print('error: ' + str(error), file=sys.stderr)
        return 2
    if args.command == 'schema':
        print(SCHEMA_WARNING, file=sys.stderr)
    if args.json:
        print(json.dumps(_json_value(result), ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    elif args.command == 'doctor':
        print(result['warning'])
        print('SQLite ' + result['sqlite_version'] + '; schema objects: ' + str(result['schema_object_count']))
    elif args.command == 'tasks':
        rows = result if args.task_command == 'list' else ([] if result is None else [result])
        for row in rows:
            print(json.dumps(_json_value(row), ensure_ascii=True, sort_keys=True, allow_nan=False))
    else:
        print('SQLite schema objects: ' + str(len(result['objects'])))
        for obj in result['objects']:
            print(obj['type'] + ' ' + json.dumps(obj['name']))
    if args.command == 'tasks' and args.task_command == 'show' and result is None:
        print('Task not found.', file=sys.stderr)
        return 3
    return 0
