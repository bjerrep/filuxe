import requests, time, os
from log import deb, inf, cri
from errorcodes import ErrorCode
import warnings, urllib3, json

warnings.simplefilter('ignore', urllib3.exceptions.SecurityWarning)


class Filuxe:
    def __init__(self, cfg, lan=True):
        self.certificate = False
        protocol = 'http://'
        if lan:
            try:
                self.certificate = cfg['lan_certificate']
                protocol = 'https://'
            except:
                pass

            self.server = f'{protocol}{cfg["lan_host"]}:{cfg["lan_port"]}'
            inf(f'filuxe LAN server is {self.server}')
            self.file_root = cfg['lan_filestorage']
            self.domain = 'LAN'
        else:
            try:
                self.certificate = cfg['wan_certificate']
                protocol = 'https://'
            except:
                pass

            self.server = f'{protocol}{cfg["wan_host"]}:{cfg["wan_port"]}'
            inf(f'filuxe WAN server is {self.server}')
            self.file_root = cfg['lan_filestorage']
            self.domain = 'WAN'
        try:
            self.write_key = cfg['wan_write_key']
        except:
            self.write_key = ''

    def download(self, filename, path):
        response = requests.get('{}/download/{}'.format(self.server, path))
        if not os.path.exists(filename):
            open(filename, 'wb').write(response.content)
        else:
            cri('local file already exists, bailing out', ErrorCode.FILE_ALREADY_EXIST)
        return ErrorCode.OK

    def upload(self, filename, path=None, touch=False):
        with open(filename) as fp:
            content = fp.read()
        if not path:
            path = filename

        if touch:
            epoch = time.time()
        else:
            epoch = os.path.getatime(filename)

        deb(f'uploading {filename} to server as {path}')
        response = requests.post('{}/upload/{}'.format(self.server, path),
                                 headers={'key': self.write_key},
                                 data=content,
                                 params={'time': epoch},
                                 verify=self.certificate)
        if response.status_code == 201:
            return ErrorCode.OK
        return ErrorCode.SERVER_ERROR

    def delete(self, path):
        response = requests.get('{}/delete/{}'.format(self.server, path),
                                headers={'key': self.write_key},
                                verify=self.certificate)
        if response.status_code == 200:
            return ErrorCode.OK
        return ErrorCode.FILE_NOT_FOUND

    def list(self, path, pretty=False, recursive=False):
        response = requests.get('{}/filelist/{}'.format(self.server, path),
                                headers={'key': self.write_key},
                                params={'recursive': recursive},
                                verify=self.certificate)
        if pretty:
            return ErrorCode.OK, json.dumps(response.json(), indent=4)
        return ErrorCode.OK, response.json()
