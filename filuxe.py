#!/usr/bin/env python3
import argparse, json, requests
from log import logger as log
from log import inf, die
from errorcodes import ErrorCode
import logging, filuxe_api, config_util


parser = argparse.ArgumentParser('filuxe')

parser.add_argument('--upload', action='store_true',
                    help='upload file given by --file with destination path and name given by --path. See --force')
parser.add_argument('--download', action='store_true',
                    help='download file')
parser.add_argument('--delete', action='store_true',
                    help='delete file given by --path')
parser.add_argument('--list', action='store_true',
                    help='get list of files and directories as json. See --pretty and --recursive')
parser.add_argument('--filelist', action='store_true',
                    help='get raw list of files. See --recursive')

parser.add_argument('--recursive', action='store_true',
                    help='get recursive --list')
parser.add_argument('--file',
                    help='local file to save or upload')
parser.add_argument('--path', default='.',
                    help='path for --list/--filelist (optional) or path and filename for all other commands')
parser.add_argument('--touch', action='store_true',
                    help='set the uploaded file timestamp to server time. Default is to keep the original timestamp')
parser.add_argument('--force', action='store_true',
                    help='allow a --upload to rewrite an existing file (which is default illegal)')

parser.add_argument('--verbose', action='store_true',
                    help='enable verbose messages')
parser.add_argument('--info', action='store_true',
                    help='enable informational messages')
parser.add_argument('--pretty', action='store_true',
                    help='pretty print json')
parser.add_argument('--config', default='config_forwarder.json',
                    help='configuration file, default config_forwarder.json')

args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.DEBUG)
elif args.info:
    log.setLevel(logging.INFO)
else:
    log.setLevel(logging.WARNING)

cfg = None

if args.config:
    try:
        cfg = config_util.load_config(args.config)
    except FileNotFoundError as e:
        die('config file not found', e, ErrorCode.FILE_NOT_FOUND)
    except json.decoder.JSONDecodeError as e:
        die(f'json error in {args.config}', e, ErrorCode.FILE_INVALID)

try:
    lan = cfg.get('lan_host')

    filuxe = filuxe_api.Filuxe(cfg, lan=lan)

    error_code = ErrorCode.UNSET

    try:
        if args.download:
            error_code = filuxe.download(args.file, args.path, args.force)
        elif args.upload:
            error_code = filuxe.upload(args.file, args.path, args.touch, args.force)
        elif args.delete:
            error_code = filuxe.delete(args.path)
        elif args.list:
            error_code, list = filuxe.list(args.path, args.pretty, args.recursive)
            print(list)
        elif args.filelist:
            error_code, file_list = filuxe.list_files(args.path, args.recursive)
            for name in file_list:
                print(name)
        else:
            die('seems that you didnt really tell me what to do ?', ErrorCode.BAD_ARGUMENTS)
    except requests.exceptions.ConnectionError:
        die('Connection refused, server might be offline?', ErrorCode.SERVER_ERROR)

    if error_code != ErrorCode.OK:
        die(f'operation failed with {error_code}')

except Exception as e:
    die('filuxe crashed', e, ErrorCode.UNHANDLED_EXCEPTION)

inf('exiting')
exit(0)
