#!/usr/bin/env python3
import argparse, traceback, json, requests
from log import logger as log
from log import inf, cri
from errorcodes import ErrorCode
import logging, filuxe_api, config_util


def die(e, error_code):
    if args.verbose:
        print(traceback.format_exc())
    cri(f'caught exception {e}', error_code)


parser = argparse.ArgumentParser('filuxe')

parser.add_argument('--upload', action='store_true',
                    help='upload file with destination path and name given by --path')
parser.add_argument('--download', action='store_true',
                    help='download file')
parser.add_argument('--delete', action='store_true',
                    help='delete file given by --path')
parser.add_argument('--list', action='store_true',
                    help='get file list')

parser.add_argument('--recursive', action='store_true',
                    help='get recursive --list')
parser.add_argument('--file',
                    help='local file to save or upload')
parser.add_argument('--path', default='/',
                    help='path for --list or path and filename for all other commands')
parser.add_argument('--touch', action='store_true',
                    help='set the uploaded file timestamp to now. Default is to keep the original timestamp')

parser.add_argument('--verbose', action='store_true',
                    help='enable debug messages')
parser.add_argument('--pretty', action='store_true',
                    help='pretty print json')
parser.add_argument('--config', default='config_forwarder.json',
                    help='configuration file, default config_forwarder.json')

args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.DEBUG)
else:
    log.setLevel(logging.WARNING)

cfg = None

if args.config:
    try:
        cfg = config_util.load_config(args.config)
    except FileNotFoundError as e:
        die(e, ErrorCode.FILE_NOT_FOUND)
    except json.decoder.JSONDecodeError as e:
        die(e, ErrorCode.FILE_INVALID)

try:
    try:
        lan = True
        file_root = cfg['lan_filestorage']
        inf('LAN filestorage root %s' % file_root)
    except KeyError:
        lan = False
        file_root = cfg['wan_filestorage']
        inf('WAN filestorage root %s' % file_root)

    filuxe = filuxe_api.Filuxe(cfg, lan=lan)

    errorcode = ErrorCode.UNSET

    try:
        if args.download:
            errorcode = filuxe.download(args.file, args.path)
        elif args.upload:
            errorcode = filuxe.upload(args.file, args.path, args.touch)
        elif args.delete:
            errorcode = filuxe.delete(args.path)
        elif args.list:
            errorcode, list = filuxe.list(args.path, args.pretty, args.recursive)
            print(list)
        else:
            cri('seems that you didnt really tell me what to do ?', ErrorCode.BAD_ARGUMENTS)
    except requests.exceptions.ConnectionError:
        cri('Connection refused, server might be offline?', ErrorCode.SERVER_ERROR)

    if errorcode != ErrorCode.OK:
        cri('critical message', errorcode)

except Exception as e:
    die(e, ErrorCode.UNHANDLED_EXCEPTION)

inf('exiting')
