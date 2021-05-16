#!/usr/bin/env python
import livetest
import pathlib, os


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


servers = livetest.Servers(clean=False)

servers.start_lan_server()
servers.start_wan_server()
# servers.start_forwarder()

make_test_set_1()

print()
input('servers are started, press any key to shutdown')

servers.close()
