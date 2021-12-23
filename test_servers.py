#!/usr/bin/env python
import livetest
import log
import pathlib, os, argparse


def make_test_set_1():
    path = 'test/filestorage_lan/'
    pathlib.Path(path + 'a:1.1.1:anytrack:anyarch:unknown.zip').touch()
    pathlib.Path(path + 'a:1.1.2:anytrack:anyarch:unknown.zip').touch()
    pathlib.Path(path + 'a:1.1.3:anytrack:anyarch:unknown.zip').touch()
    pathlib.Path(path + 'b:1.1.3:anytrack:anyarch:unknown.zip').touch()
    pathlib.Path(os.path.join(path, 'second')).mkdir(exist_ok=True)
    pathlib.Path(path + 'second/' + 'c:1.1.1:anytrack:anyarch:unknown.zip').touch()
    pathlib.Path(path + 'second/' + 'c:1.1.2:anytrack:anyarch:unknown.zip').touch()
    pathlib.Path(path + 'second/' + 'c:1.1.3:anytrack:anyarch:unknown.zip').touch()


parser = argparse.ArgumentParser('test_servers')

parser.add_argument('--all', action='store_true',
                    help='start everything, the lan server, wan server and forwarder (default)')
parser.add_argument('--lan', action='store_true',
                    help='start lan server')
parser.add_argument('--wan', action='store_true',
                    help='start wan server')
parser.add_argument('--forwarder', action='store_true',
                    help='start forwarder')
parser.add_argument('--onlydata', action='store_true',
                    help='just touch the testfiles and exit')

args = parser.parse_args()

if args.onlydata:
    make_test_set_1()
    exit(0)

if not args.all and not args.lan and not args.wan and not args.forwarder:
    args.all = True

servers = livetest.Servers(clean=False)

message = ''
if args.all or args.lan:
    servers.start_lan_server('config/lan/live_test_http_lan_config.json')
    message += f'LAN server started\nLaunch: "{servers.lan_server.launch}"\n'
if args.all or args.wan:
    servers.start_wan_server('config/wan/live_test_https_wan_config.json')
    message += f'WAN server started\nLaunch: "{servers.wan_server.launch}"\n'
if args.all or args.forwarder:
    servers.start_forwarder(
            'config/fwd/live_test_http_https_fwd_config.json',
            'config/rules/live_test_forwarder_as_deleter.json')
    message += f'Forwarder started\nLaunch: "{servers.forwarder.launch}"\n'

log.inf('generating testset in lan filestorage')
make_test_set_1()

print(f'\n{message}')

input('press any key to shutdown')

servers.close()
