#!/usr/bin/env python
import unittest, json, os, pexpect, time, shutil, pathlib, requests, sys

TEST_DIR = 'test'
LAN_CONFIG = os.path.join(TEST_DIR, 'test_lan_config.json')
WAN_CONFIG = os.path.join(TEST_DIR, 'test_wan_config.json')
FORWARDER_CONFIG = os.path.join(TEST_DIR, 'test_forwarder_config.json')
FORWARDER_RULES = os.path.join(TEST_DIR, 'test_forwarder_rules.json')
TIMEOUT = 2


def deb(message):
    print(message)


def fat(message):
    print(message)


def write_lan_config():
    config = {
        "lan_filestorage": f"{TEST_DIR}/filestorage_lan",
        "lan_host": "localhost",
        "lan_port": 8000
    }
    with open(LAN_CONFIG, 'w') as f:
        f.write(json.dumps(config))

    pathlib.Path(config['lan_filestorage']).mkdir(exist_ok=True)

    return config


def write_wan_config():
    config = {
        "wan_filestorage": f"{TEST_DIR}/filestorage_wan",
        "wan_host": "localhost",
        "wan_port": 9000,
        "wan_write_key": "devel",
        "wan_certificate": "certificates/cert.pem.devel",
        "certificates": ["certificates/cert.pem.devel", "certificates/key.pem.devel"],
        "username": "name",
        "password": "pwd"
    }
    with open(WAN_CONFIG, 'w') as f:
        f.write(json.dumps(config))

    pathlib.Path(config['wan_filestorage']).mkdir(exist_ok=True)

    return config


def write_forwarder_config():
    config = {
        "lan_filestorage": f"{TEST_DIR}/filestorage_lan",
        "lan_host": "localhost",
        "lan_port": 8000,
        "wan_host": "localhost",
        "wan_port": 9000,
        "wan_certificate": "certificates/cert.pem.devel",
        "wan_write_key": "devel"
    }
    with open(FORWARDER_CONFIG, 'w') as f:
        f.write(json.dumps(config))

    return config


def write_forwarder_rules():
    rules = {"default": {}, "dirs": {}}

    with open(FORWARDER_RULES, 'w') as f:
        f.write(json.dumps(rules))

    return rules


def write_file(filename, content):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        f.write(content)


class TestStringMethods(unittest.TestCase):

    def wait_for_server(self, config, lan):
        ready = False
        attempts = 10
        while not ready and attempts:
            try:
                if lan:
                    r = requests.get(f'http://{config["lan_host"]}:{config["lan_port"]}/api/status')
                else:
                    # launch this test script with PYTHONWARNINGS="ignore:Unverified HTTPS request" to ignore
                    # the warning about the lacking SSL verification.
                    r = requests.get(f'https://{config["wan_host"]}:{config["wan_port"]}/api/status', verify=False)
                if r.status_code == 200:
                    ready = True
                else:
                    time.sleep(0.1)
                    attempts -= 1
            except requests.ConnectionError:
                time.sleep(0.1)
                attempts -= 1
        return attempts

    def setUp(self):
        if os.path.exists(TEST_DIR):
            shutil.rmtree(TEST_DIR)
        try:
            os.mkdir(TEST_DIR)
        except Exception as e:
            fat(f'could not make test dir {e}')
            raise e

        self.lan_config = write_lan_config()
        self.wan_config = write_wan_config()
        self.forwarder_config = write_forwarder_config()
        write_forwarder_rules()

        if True:
            self.lan_server = pexpect.spawn(f'./filuxe_server.py --config {LAN_CONFIG} --verbose', encoding='utf-8')
            self.lan_server.logfile = sys.stderr
            ready = self.wait_for_server(self.lan_config, lan=True)
            self.assertTrue(ready)

        if True:
            self.wan_server = pexpect.spawn(f'./filuxe_server.py --config {WAN_CONFIG} --verbose', encoding='utf-8')
            self.wan_server.logfile = sys.stderr
            ready = self.wait_for_server(self.wan_config, lan=False)
            self.assertTrue(ready)

        if True:
            self.forwarder = \
                pexpect.spawn(f'./filuxe_forwarder.py --config {FORWARDER_CONFIG} --verbose --rules {FORWARDER_RULES} --verbose',
                              encoding='utf-8')
            self.forwarder.logfile = sys.stderr
            self.forwarder.expect('filuxe forwarder is ready')

    def tearDown(self):
        self.lan_server.close()
        self.wan_server.close()
        self.forwarder.close()
        shutil.rmtree(TEST_DIR)

    def test_a_quick_spin_direct_file(self):
        # write a file directly into lan filestorage and verify that it appears in wan filestorage
        write_file(os.path.join(self.lan_config['lan_filestorage'], 'direct_write'), 'test')
        self.wan_server.expect('writing file test/filestorage_wan/direct_write', timeout=TIMEOUT)
        self.assertTrue(os.path.exists(os.path.join(self.wan_config['wan_filestorage'], 'direct_write')))

        # - and then delete the file from lan filestorage and verify that it disappears from wan filestorage
        os.remove(os.path.join(self.lan_config['lan_filestorage'], 'direct_write'))
        self.wan_server.expect('deleting test/filestorage_wan/direct_write', timeout=TIMEOUT)
        self.assertFalse(os.path.exists(os.path.join(self.wan_config['wan_filestorage'], 'direct_write')))

    def test_a_quick_spin_filuxe_access(self):
        # upload a local file to lan filestorage via http via the filuxe script
        source_file = os.path.join(TEST_DIR, 'http_upload')
        write_file(source_file, 'test')
        dest_file = 'testpath/upload'
        pexpect.run(f'./filuxe.py --config {LAN_CONFIG} --path {dest_file} --file {source_file} --touch --upload')
        self.wan_server.expect('writing file test/filestorage_wan/testpath/upload', timeout=TIMEOUT)
        self.assertTrue(os.path.exists(os.path.join(self.wan_config['wan_filestorage'], dest_file)))
        os.remove(source_file)
        self.assertFalse(os.path.exists(source_file))

        # and then download the file from the wan server (typically expected to be a wget from products instead)
        pexpect.run(f'./filuxe.py --config {WAN_CONFIG} --path {dest_file} --file {source_file} --download')
        self.assertTrue(os.path.exists(source_file))


if __name__ == '__main__':
    unittest.main()
