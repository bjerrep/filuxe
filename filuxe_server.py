#!/usr/bin/env python3
import argparse, traceback, json
from log import logger as log
from log import inf, cri
from errorcodes import ErrorCode
import logging, filuxe_server_app, config_util


def die(e, error_code):
    if args.verbose:
        print(traceback.format_exc())
    cri(f'caught exception {e}', error_code)


parser = argparse.ArgumentParser('filuxe_server')
parser.add_argument('--verbose', action='store_true',
                    help='enable all messages (including flask)')
parser.add_argument('--debug', action='store_true',
                    help='enable debug messages')
parser.add_argument('--config', default='config.json',
                    help='configuration file')

args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.DEBUG)
else:
    if args.debug:
        log.setLevel(logging.INFO)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

cfg = None

if args.config:
    try:
        cfg = config_util.load_config(args.config)
    except FileNotFoundError as e:
        die(e, ErrorCode.FILE_NOT_FOUND)
    except json.decoder.JSONDecodeError as e:
        die(e, ErrorCode.FILE_INVALID)

try:
    errorcode = filuxe_server_app.start(args, cfg)

    if errorcode != ErrorCode.OK:
        cri('critical message', errorcode)

except Exception as e:
    die(e, ErrorCode.UNHANDLED_EXCEPTION)


inf('exiting')
