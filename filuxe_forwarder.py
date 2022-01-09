#!/usr/bin/env python3
import argparse, json, traceback
from log import logger as log
from log import inf, die
from errorcodes import ErrorCode
import logging, filuxe_forwarder_app, config_util


parser = argparse.ArgumentParser('filuxe_forwarder')

parser.add_argument('--config', default='config_forwarder.json',
                    help='configuration file, default config_forwarder.json')
parser.add_argument('--rules',
                    help='rules json file. Default is an empty rule set forwarding everything')

parser.add_argument('--templaterule', action='store_true',
                    help='make an example rules.json file')
parser.add_argument('--dryrun', action='store_true',
                    help='don\'t actually delete files')

parser.add_argument('--verbose', action='store_true',
                    help='enable verbose messages')
parser.add_argument('--info', action='store_true',
                    help='enable informational messages')

args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.DEBUG)
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    logging.getLogger('watchdog').setLevel(logging.INFO)
else:
    if args.info:
        log.setLevel(logging.INFO)
    else:
        log.setLevel(logging.WARNING)
    logging.getLogger('werkzeug').setLevel(logging.ERROR)

cfg = None

# generating a template from an existing file structure would be nice to have as well...
if args.templaterule:
    product_release_image = {"include": "img", "exclude": "zip"}
    product_release = {"include": "zip", "maxfiles": "unlimited"}
    product_candidate = {"include": "zip,elf"}
    product = {"maxfiles": 2}
    root = {"maxfiles": 10, "export": True}
    CONFIG = {"default": root, "dirs": {
        "product/release/image": product_release_image,
        "product/candidate": product_candidate,
        "product/release": product_release,
        "product": product}}
    jsn = json.dumps(CONFIG, indent=4, sort_keys=True)
    print(jsn)
    exit(0)

if args.config:
    try:
        cfg = config_util.load_config(args.config)
        inf(f'loaded configuration {args.config}')
    except FileNotFoundError as e:
        die('config file not found', e)
    except json.decoder.JSONDecodeError as e:
        die(f'json error in {args.config}', e, ErrorCode.FILE_INVALID)

LOADED_RULES = None
if args.rules:
    try:
        LOADED_RULES = config_util.load_config(args.rules)
        inf(f'loaded rules file {args.rules}')
    except json.decoder.JSONDecodeError as e:
        die(f'json error in {args.rules}', e, ErrorCode.FILE_INVALID)
    except:
        die(f'loading {args.rules} failed')
else:
    inf('no rules specified, running with default rules forwarding everything')

try:
    errcode = filuxe_forwarder_app.start(args, cfg, LOADED_RULES)

    if errcode != ErrorCode.OK:
        die('critical message', errcode)

except Exception as e:
    if log.level <= logging.INFO:
        traceback.print_exc()
    die('forwarder crashed', e, ErrorCode.UNHANDLED_EXCEPTION)

inf('exiting')
