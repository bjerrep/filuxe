#!/usr/bin/env python
import unittest, json, os, pexpect, time, shutil, pathlib, requests, sys, io, contextlib

TEST_DIR = 'test'
LAN_CONFIG = os.path.join(TEST_DIR, 'test_lan_config.json')
WAN_CONFIG = os.path.join(TEST_DIR, 'test_wan_config.json')
FORWARDER_CONFIG = os.path.join(TEST_DIR, 'test_forwarder_config.json')
FORWARDER_RULES = os.path.join(TEST_DIR, 'test_forwarder_rules.json')
TIMEOUT = 5
WRITE_DELAY = 1


def deb(message):
    print(message)


def rel(message):
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
        f.write(json.dumps(config, indent=4))

    pathlib.Path(config['lan_filestorage']).mkdir(exist_ok=True)

    return config


def write_wan_config():
    config = {
        "wan_filestorage": f"{TEST_DIR}/filestorage_wan",
        "wan_host": "localhost",
        "wan_port": 9000,
        "write_key": "devel",
        "wan_certificate": f"{TEST_DIR}/certificates/cert.pem.devel",
        "certificates": [f"{TEST_DIR}/certificates/cert.pem.devel", f"{TEST_DIR}/certificates/key.pem.devel"],
        "username": "name",
        "password": "pwd"
    }
    with open(WAN_CONFIG, 'w') as f:
        f.write(json.dumps(config, indent=4))

    pathlib.Path(config['wan_filestorage']).mkdir(exist_ok=True)

    return config


def write_forwarder_config():
    config = {
        "lan_filestorage": f"{TEST_DIR}/filestorage_lan",
        "lan_host": "localhost",
        "lan_port": 8000,
        "wan_host": "localhost",
        "wan_port": 9000,
        "wan_certificate": f"{TEST_DIR}/certificates/cert.pem.devel",
        "certificates": [f"{TEST_DIR}/certificates/cert.pem.devel", f"{TEST_DIR}/certificates/key.pem.devel"],
        "write_key": "devel"
    }
    with open(FORWARDER_CONFIG, 'w') as f:
        f.write(json.dumps(config, indent=4))

    return config


def write_forwarder_rules():
    rules = {"default": {}, "dirs": {}}

    with open(FORWARDER_RULES, 'w') as f:
        f.write(json.dumps(rules, indent=4))

    return rules


def generate_certificates():
    cert_dir = '%s/certificates' % TEST_DIR
    os.makedirs(cert_dir, exist_ok=True)
    os.chdir(cert_dir)
    os.system('openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem.devel -keyout key.pem.devel -days 365'
              ' -subj "/C=US/ST=NY/L=New York/O=Foo Corp/OU=Bar Div/CN=localhost"')
    os.chdir('../..')


def write_file(filename, content):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, 'w') as f:
        f.write(content)


class Servers:
    lan_server = None
    wan_server = None
    forwarder = None

    def __init__(self, clean=True):
        if clean:
            if os.path.exists(TEST_DIR):
                shutil.rmtree(TEST_DIR)
            try:
                os.mkdir(TEST_DIR)
            except Exception as e:
                fat(f'could not make test dir {e}')
                raise e

        generate_certificates()

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

    def start_lan_server(self):
        rel('----------- starting LAN server ----------')
        self.lan_config = write_lan_config()
        command = f'./filuxe_server.py --config {LAN_CONFIG} --verbose'
        rel(f'lan server command: {command}')
        self.lan_server = pexpect.spawn(command, encoding='utf-8')
        self.lan_server.logfile = sys.stderr
        ready = self.wait_for_server(self.lan_config, lan=True)
        if not ready:
            raise Exception('LAN server didn\'t start')

    def start_wan_server(self):
        rel('----------- starting WAN server ----------')
        self.wan_config = write_wan_config()
        self.wan_server = pexpect.spawn(f'./filuxe_server.py --config {WAN_CONFIG} --verbose', encoding='utf-8')
        self.wan_server.logfile = sys.stderr
        ready = self.wait_for_server(self.wan_config, lan=False)
        if not ready:
            raise Exception('WAN server didn\'t start')

    def start_forwarder(self):
        rel('----------- starting forwarder ----------')
        self.forwarder_config = write_forwarder_config()
        write_forwarder_rules()
        self.forwarder = \
            pexpect.spawn(
                f'./filuxe_forwarder.py --config {FORWARDER_CONFIG} --rules {FORWARDER_RULES} --verbose',
                encoding='utf-8')
        self.forwarder.logfile = sys.stderr
        self.forwarder.expect('filuxe forwarder is ready')

    def start_servers_and_forwarder(self):
        self.start_lan_server()
        self.start_wan_server()
        self.start_forwarder()

    def close_lan_server(self):
        if self.lan_server:
            self.lan_server.close()
            self.lan_server = None

    def close_wan_server(self):
        if self.wan_server:
            self.wan_server.close()
            self.wan_server = None

    def close_forwarder(self):
        if self.forwarder:
            self.forwarder.close()
            self.forwarder = None

    def close(self):
        self.close_lan_server()
        self.close_wan_server()
        self.close_forwarder()


class TestStringMethods(unittest.TestCase):

    def setUp(self):
        self.servers = Servers()
        self.servers.start_servers_and_forwarder()

    def tearDown(self):
        self.servers.close()
        shutil.rmtree(TEST_DIR)

    def test_a_quick_spin_direct_file(self):
        # write a file directly into lan filestorage and verify that it appears in wan filestorage
        lan_file = os.path.join(self.servers.lan_config['lan_filestorage'], 'direct_write')
        write_file(lan_file, 'test')
        # wait for the wan server to make the write
        self.servers.wan_server.expect('writing file test/filestorage_wan/direct_write', timeout=TIMEOUT)
        wan_file = os.path.join(self.servers.wan_config['wan_filestorage'], 'direct_write')

        time.sleep(WRITE_DELAY)
        self.assertTrue(os.path.exists(wan_file))
        # - and then delete the file from lan filestorage and verify that it disappears from wan filestorage
        os.remove(lan_file)
        self.servers.wan_server.expect('deleting test/filestorage_wan/direct_write', timeout=TIMEOUT)

        time.sleep(WRITE_DELAY)
        self.assertFalse(os.path.exists(wan_file))

    def test_a_quick_spin_filuxe_access(self):
        # upload a local file to lan filestorage via http via the filuxe script
        source_file = os.path.join(TEST_DIR, 'http_upload')
        write_file(source_file, 'test')
        dest_file = 'testpath/upload'
        pexpect.run(f'./filuxe.py --config {LAN_CONFIG} --path {dest_file} --file {source_file} --touch --upload')
        self.servers.wan_server.expect('writing file test/filestorage_wan/testpath/upload', timeout=TIMEOUT)
        time.sleep(WRITE_DELAY)
        self.assertTrue(os.path.exists(os.path.join(self.servers.wan_config['wan_filestorage'], dest_file)))
        os.remove(source_file)
        time.sleep(WRITE_DELAY)
        self.assertFalse(os.path.exists(source_file))

        # and then download the file from the wan server (typically expected to be a wget from products instead)
        pexpect.run(f'./filuxe.py --config {WAN_CONFIG} --path {dest_file} --file {source_file} --download')
        self.assertTrue(os.path.exists(source_file))


if __name__ == '__main__':
    import __main__
    unittest.main(failfast=True)
    buf = io.StringIO()
    suite = unittest.TestLoader().loadTestsFromModule(__main__)
    with contextlib.redirect_stdout(buf):
        unittest.TextTestRunner(stream=buf).run(suite)
    print(buf.getvalue())
