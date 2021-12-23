#!/usr/bin/env python3
import argparse, json
from log import logger as log
from log import inf, die
from errorcodes import ErrorCode
import logging, filuxe_server_app, config_util


parser = argparse.ArgumentParser('filuxe_server')
parser.add_argument('--verbose', action='store_true',
                    help='enable all messages (including flask)')
parser.add_argument('--info', action='store_true',
                    help='enable informational messages')
parser.add_argument('--config', default='config.json',
                    help='configuration file')

args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.DEBUG)
else:
    if args.info:
        log.setLevel(logging.INFO)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

cfg = None

if args.config:
    try:
        cfg = config_util.load_config(args.config)
    except FileNotFoundError as e:
        die(f'config file {args.config} not found', e, ErrorCode.FILE_NOT_FOUND)
    except json.decoder.JSONDecodeError as e:
        die(f'json error in config file {args.config}', e, ErrorCode.FILE_INVALID)

try:
    errorcode = filuxe_server_app.start(args, cfg)

    if errorcode != ErrorCode.OK:
        die('critical message', errorcode)

except Exception as e:
    die(e, ErrorCode.UNHANDLED_EXCEPTION)


inf('exiting')
