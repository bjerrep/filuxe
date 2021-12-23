#!/usr/bin/env python
from config_util import load_config
import unittest, json, os, pexpect, time, shutil, requests, sys, io, contextlib

TEST_DIR = 'test'
LAN_CONFIG = os.path.join(TEST_DIR, 'test_lan_config.json')
WAN_CONFIG = os.path.join(TEST_DIR, 'test_wan_config.json')
TIMEOUT = 5
WRITE_DELAY = 1
LOGSWITCH = '--info'


def deb(message):
    print(message)


def rel(message):
    print(message)


def fat(message):
    print(message)


def load_json(filename):
    fqn = os.path.realpath(filename)
    with open(fqn) as f:
        content = f.read()
        return json.loads(content)


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


def delete_file(filename):
    os.remove(filename)


def build_test_file_set(root, dir, nof_file_sets, offset):
    test_files = []
    for i in range(nof_file_sets):
        test_files.append(os.path.join(root, dir, f'a:1.0.{i + offset}:root.zip'))
        test_files.append(os.path.join(root, dir, f'b:1.0.{i + offset}:root.zip'))
        test_files.append(os.path.join(root, dir, f'unversioned{i + offset}.zip'))
        test_files.append(os.path.join(root, dir, f'plain{i + offset}.txt'))
    return test_files


def write_testfiles(root, dir, nof_file_sets, offset=0):
    test_files = build_test_file_set(root, dir, nof_file_sets, offset)
    for test_file in test_files:
        write_file(test_file, 'test')
    return test_files


def verify_testfiles(root, dir, nof_file_sets, offset=0):
    test_files = build_test_file_set(root, dir, nof_file_sets, offset)
    for test_file in test_files:
        if not os.path.exists(test_file):
            return test_file
    return None


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

    def wait_for_server(self, config, lan):
        ready = False
        attempts = 50
        while not ready and attempts:
            try:
                if lan:
                    r = requests.get(f'http://{config["lan_host"]}:{config["lan_port"]}/api/status', timeout=0.1)
                else:
                    # launch this test script with PYTHONWARNINGS="ignore:Unverified HTTPS request" to ignore
                    # the warning about the lacking SSL verification.
                    r = requests.get(f'https://{config["wan_host"]}:{config["wan_port"]}/api/status', verify=False)
                if r.status_code == 200:
                    ready = True
                else:
                    time.sleep(0.1)
                    attempts -= 1

            except (requests.ConnectionError, requests.ReadTimeout):
                time.sleep(0.1)
                attempts -= 1
        return attempts

    def start_lan_server(self, config):
        rel('----------- starting LAN server ----------')
        self.lan_config = load_json(config)
        command = f'./filuxe_server.py --config {config} {LOGSWITCH}'
        rel(f'lan server command: {command}')
        self.lan_server = pexpect.spawn(command, encoding='utf-8')
        self.lan_server.launch = command
        self.lan_server.logfile_read = sys.stderr
        ready = self.wait_for_server(self.lan_config, lan=True)
        if not ready:
            raise Exception('LAN server didn\'t start')

    def start_wan_server(self, config):
        rel('----------- starting WAN server ----------')
        generate_certificates()
        self.wan_config = load_json(config)
        command = f'./filuxe_server.py --config {config} {LOGSWITCH}'
        rel(f'wan server command: {command}')
        self.wan_server = pexpect.spawn(command, encoding='utf-8')
        self.wan_server.launch = command
        self.wan_server.logfile_read = sys.stderr
        ready = self.wait_for_server(self.wan_config, lan=False)
        if not ready:
            raise Exception('WAN server didn\'t start')

    def start_forwarder(self, config=None, rules=None):
        rel('----------- starting forwarder ----------')
        self.forwarder_config = load_json(config)
        if rules:
            _rules = f'--rules {rules}'
        else:
            _rules = ''
        command = f'./filuxe_forwarder.py --config {config} {_rules} {LOGSWITCH}'
        rel(f'forwarder command: {command}')
        self.forwarder = pexpect.spawn(command, encoding="utf-8")
        self.forwarder.launch = command
        self.forwarder.logfile_read = sys.stderr
        self.forwarder.expect('filuxe forwarder is ready', timeout=5)

    def start_servers_and_forwarder(self, fwd_config, fwd_rules):
        self.start_lan_server('config/lan/live_test_http_lan_config.json')
        self.start_wan_server('config/wan/live_test_https_wan_config.json')
        self.start_forwarder(fwd_config, fwd_rules)

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


class BasicForwarding(unittest.TestCase):
    """
    Debugging in the testcases below gets very tedious very very quickly.
    Alternatively set clean_test_data to False and manually start the processes using
    the launch lines which are printed out after a test has terminated.
    """
    def setUp(self):
        # default is clean_test_data equal True so that testdata is rewritten
        # at test start and testdata are removed at test end.
        self.clean_test_data = True
        self.servers = Servers(clean=self.clean_test_data)
        self.servers.start_servers_and_forwarder(
            'config/fwd/live_test_http_https_fwd_config.json',
            'config/rules/live_test_forwarder_as_deleter.json')

    def tearDown(self):
        self.servers.close()
        if self.clean_test_data:
            shutil.rmtree(TEST_DIR)

    def test_a_quick_spin_direct_file(self):
        print("""
        --------------------------------------------------------------
        test_a_quick_spin_direct_file
        write a file directly into lan filestorage and verify that it
        appears in wan filestorage using an already started forwarder
        --------------------------------------------------------------
        """)

        # write the file direct_write.zip in lan filestorage root
        lan_file = os.path.join(self.servers.lan_config['lan_filestorage'], 'direct_write.zip')
        write_file(lan_file, 'written by test_a_quick_spin_direct_file')

        # wait for the wan server to make the write
        self.servers.wan_server.expect('writing file "test/filestorage_wan/direct_write.zip"', timeout=TIMEOUT)
        wan_file = os.path.join(self.servers.wan_config['wan_filestorage'], 'direct_write.zip')

        time.sleep(WRITE_DELAY)
        self.assertTrue(os.path.exists(wan_file))
        # - and then delete the file from lan filestorage and verify that it disappears from wan filestorage
        os.remove(lan_file)
        self.servers.wan_server.expect('deleting file "test/filestorage_wan/direct_write.zip"', timeout=TIMEOUT)

        time.sleep(WRITE_DELAY)
        self.assertFalse(os.path.exists(wan_file))

    def test_a_quick_spin_filuxe_access(self):
        print("""
        --------------------------------------------------------------
        test_a_quick_spin_filuxe_access
        upload a local file to lan filestorage via http via the
        filuxe script and verify that it appears on the wan filestorage
        --------------------------------------------------------------
        """)

        source_file = os.path.join(TEST_DIR, 'http_upload')
        write_file(source_file, 'test')

        dest_file = 'testpath/upload.zip'
        lan_config = 'config/lan/live_test_http_lan_config.json'
        filuxe_command = f'./filuxe.py --config {lan_config} --path {dest_file}'\
                         f' --file {source_file} --touch --upload --force'
        rel(f'filuxe upload command: {filuxe_command}')
        pexpect.run(filuxe_command)

        self.servers.wan_server.expect('writing file "test/filestorage_wan/testpath/upload.zip"', timeout=TIMEOUT)
        time.sleep(WRITE_DELAY)
        self.assertTrue(os.path.exists(os.path.join(self.servers.wan_config['wan_filestorage'], dest_file)))
        os.remove(source_file)
        time.sleep(WRITE_DELAY)
        self.assertFalse(os.path.exists(source_file))

        # and then download the file from the wan server (typically expected to be a wget from products instead)
        wan_config = 'config/wan/live_test_https_wan_config.json'
        filuxe_command = f'./filuxe.py --config {wan_config} --path {dest_file} --file {source_file} --download'
        rel(f'filuxe download command: {filuxe_command}')
        pexpect.run(filuxe_command)

        self.assertTrue(os.path.exists(source_file))


class BasicForwarderAsDeleter(unittest.TestCase):
    """
    See comment regarding debugging in BasicForwarding
    """
    def setUp(self):
        # default is clean_test_data equal True so that testdata is rewritten
        # at test start and testdata are removed at test end.
        self.clean_test_data = True
        self.servers = Servers(clean=self.clean_test_data)

    def tearDown(self):
        self.servers.close()
        if self.clean_test_data:
            shutil.rmtree(TEST_DIR)

    def test_forward_deleter(self):
        print("""
        --------------------------------------------------------------
        test_forward_deleter
        write some files in lan filestorage and verify that the forwarder deleter
        processes the rules correctly
        --------------------------------------------------------------""")

        self.servers.start_lan_server(config='config/lan/live_test_http_lan_config.json')
        self.servers.start_forwarder(config='config/fwd/live_test_forwarder_as_deleter_config.json',
                                     rules='config/rules/live_test_forwarder_as_deleter.json')

        config = self.servers.forwarder_config

        root = config['lan_filestorage']

        for i in range(4):
            write_file(os.path.join(root, f'a:1.0.{i}:root.zip'), 'test')

        self.servers.forwarder.expect('idle')


class SyncAtStartup(unittest.TestCase):
    """
    See comment regarding debugging in BasicForwarding
    """
    def setUp(self):
        # default is clean_test_data equal True so that testdata is rewritten
        # at test start and testdata are removed at test end.
        self.clean_test_data = True
        self.servers = Servers(clean=self.clean_test_data)
        self.servers.start_lan_server(config='config/lan/live_test_http_lan_config.json')
        self.servers.start_wan_server(config='config/wan/live_test_https_wan_config.json')

    def tearDown(self):
        self.servers.close()
        if self.clean_test_data:
            shutil.rmtree(TEST_DIR)

    def test_sync_at_startup(self):
        print("""
        --------------------------------------------------------------
        test_sync_at_startup
        write some files in lan filestorage and start the forwarder with
        "sync_at_startup" which will then upload the files to the wan server
        --------------------------------------------------------------""")

        config = 'config/fwd/live_test_http_https_fwd_config.json'
        lan_root = load_config(config)['lan_filestorage']
        wan_root = self.servers.wan_config['wan_filestorage']

        write_testfiles(lan_root, '', 4)

        self.servers.start_forwarder(config=config, rules=None)
        self.servers.forwarder.expect('idle')

        missing_filename = verify_testfiles(wan_root, '', 4)
        self.assertFalse(missing_filename)


if __name__ == '__main__':
    if True:
        import __main__
        unittest.main(failfast=True)
        suite = unittest.TestLoader().loadTestsFromModule(__main__)
    else:
        suite = unittest.TestLoader().loadTestsFromTestCase(SyncAtStartup)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        unittest.TextTestRunner(stream=buf).run(suite)
    print(buf.getvalue())
