import requests, time, os
from log import deb, inf, err, cri
from errorcodes import ErrorCode
from util import chunked_reader
import warnings, urllib3, json

warnings.simplefilter('ignore', urllib3.exceptions.SecurityWarning)


class Filuxe:
    def __init__(self, cfg, lan=True, force=False):
        self.certificate = False
        protocol = 'http://'
        self.force = force
        try:
            if lan:
                self.domain = 'LAN'
                try:
                    self.certificate = cfg['lan_certificate']
                    protocol = 'https://'
                except:
                    pass

                self.server = f'{protocol}{cfg["lan_host"]}:{cfg["lan_port"]}'
                inf(f'filuxe LAN server is {self.server}')
                self.file_root = cfg.get('lan_filestorage')

            else:
                self.domain = 'WAN'
                try:
                    self.certificate = cfg['wan_certificate']
                    protocol = 'https://'
                except:
                    pass

                self.server = f'{protocol}{cfg["wan_host"]}:{cfg["wan_port"]}'
                inf(f'filuxe WAN server is {self.server}')
                try:
                    self.file_root = cfg['wan_filestorage']
                except:
                    inf('loading forwarder configuration')
                    self.file_root = cfg['lan_filestorage']

        except KeyError as e:
            err(f'expected a {e} entry in the configuration file', ErrorCode.MISSING_KEY)

        try:
            self.write_key = cfg['write_key']
        except:
            self.write_key = ''

    @staticmethod
    def load_config_file(filename):
        with open(filename) as f:
            return json.loads(f.read())

    def download(self, filename, path):
        url = f'{self.server}/download/{path}'
        deb(f'download {url}')
        response = requests.get(url,
                                verify=self.certificate)
        if not os.path.exists(filename):
            open(filename, 'wb').write(response.content)
        else:
            cri('local file already exists, bailing out', ErrorCode.FILE_ALREADY_EXIST)
        return ErrorCode.OK

    def upload(self, filename, path=None, touch=False, force=False):
        if not path:
            path = filename

        if touch:
            epoch = time.time()
        else:
            epoch = os.path.getatime(filename)

        if self.force:
            force = True

        size = os.path.getsize(filename)
        deb(f'uploading {filename} {size:,} bytes to server as {path}')
        index = 0
        offset = 0

        if not size:
            response = requests.post('{}/upload/{}'.format(self.server, path),
                                     headers={'key': self.write_key},
                                     data='',
                                     params={'time': epoch, 'force': force},
                                     verify=self.certificate)
        else:
            try:
                for chunk in chunked_reader(filename):
                    offset = index + len(chunk)
                    response = requests.post('{}/upload/{}'.format(self.server, path),
                                             headers={'key': self.write_key,
                                                      'Content-Type': 'application/octet-stream',
                                                      'Content-length': str(size),
                                                      'Content-Range': 'bytes %s-%s/%s' % (index, offset, size)},
                                             data=chunk,
                                             params={'time': epoch, 'force': force},
                                             verify=self.certificate)
                    index = offset
            except Exception as e:
                print(e)

        try:
            if response.status_code == 201:
                return ErrorCode.OK
            if response.status_code == 403:
                return ErrorCode.FILE_ALREADY_EXIST
        except:
            pass
        return ErrorCode.SERVER_ERROR

    def delete(self, path):
        response = requests.get('{}/delete/{}'.format(self.server, path),
                                headers={'key': self.write_key},
                                verify=self.certificate)
        if response.status_code == 200:
            return ErrorCode.OK
        return ErrorCode.FILE_NOT_FOUND

    def list(self, path, pretty=False, recursive=False):
        response = requests.get(f'{self.server}/filelist/{path}',
                                headers={'key': self.write_key},
                                params={'recursive': recursive},
                                verify=self.certificate)
        if response.status_code != 200:
            return ErrorCode.SERVER_ERROR, response.reason
        if pretty:
            return ErrorCode.OK, json.dumps(response.json(), indent=4)
        return ErrorCode.OK, response.json()

    def list_files(self, path, recursive=False):
        response = requests.get('{}/filelist/{}'.format(self.server, path),
                                headers={'key': self.write_key},
                                params={'recursive': recursive},
                                verify=self.certificate)
        jsn = response.json()
        return ErrorCode.OK, list(jsn['filelist'][path].keys())
