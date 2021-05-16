#!/usr/bin/env python3
import argparse, json, traceback
from log import logger as log
from log import inf, cri
from errorcodes import ErrorCode
import logging, filuxe_forwarder_app, config_util


def die(e, error_code):
    if args.verbose:
        print(traceback.format_exc())
    cri(f'caught exception {e}', error_code)


parser = argparse.ArgumentParser('filuxe_forwarder')

parser.add_argument('--templaterule', action='store_true',
                    help='make an example rules.json file')
parser.add_argument('--rules', default='rules.json',
                    help='rules json file, default rules.json')
parser.add_argument('--dryrun', action='store_true',
                    help='don\'t actually delete files')

parser.add_argument('--verbose', action='store_true',
                    help='enable debug messages')
parser.add_argument('--debug', action='store_true',
                    help='enable debug messages')
parser.add_argument('--config', default='config_forwarder.json',
                    help='configuration file, default config_forwarder.json')

args = parser.parse_args()

if args.verbose:
    log.setLevel(logging.DEBUG)
else:
    if args.debug:
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
    config = {"default": root, "dirs": {
        "product/release/image": product_release_image,
        "product/candidate": product_candidate,
        "product/release": product_release,
        "product": product}}
    jsn = json.dumps(config, indent=4, sort_keys=True)
    print(jsn)
    exit(0)

if args.config:
    try:
        cfg = config_util.load_config(args.config)
        inf(f'loaded configuration {args.config}')
    except FileNotFoundError as e:
        die(e, ErrorCode.FILE_NOT_FOUND)
    except json.decoder.JSONDecodeError as e:
        die(e, ErrorCode.FILE_INVALID)

rules = None
try:
    rules = config_util.load_config(args.rules)
    inf(f'loaded rules file {args.rules}')
except json.decoder.JSONDecodeError as e:
    die(e, ErrorCode.FILE_INVALID)
except FileNotFoundError:
    inf(f'loading {args.rules} failed, running with default rules')

try:
    errcode = filuxe_forwarder_app.start(args, cfg, rules)

    if errcode != ErrorCode.OK:
        cri('critical message', errcode)

except Exception as e:
    if log.level <= logging.INFO:
        traceback.print_exc()
    die(e, ErrorCode.UNHANDLED_EXCEPTION)

inf('exiting')
