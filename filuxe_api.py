import requests, time, os
from log import deb, inf, cri
from errorcodes import ErrorCode
from util import chunked_reader
import warnings, urllib3, json

warnings.simplefilter('ignore', urllib3.exceptions.SecurityWarning)


class Filuxe:
    def __init__(self, cfg, lan=True):
        self.certificate = False
        protocol = 'http://'
        try:
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
                try:
                    self.file_root = cfg['wan_filestorage']
                except:
                    # its the forwarder that runs here...
                    self.file_root = cfg['lan_filestorage']
                self.domain = 'WAN'
        except KeyError as e:
            cri(f'expected a {e} entry in the configuration file', ErrorCode.MISSING_KEY)
        try:
            self.write_key = cfg['wan_write_key']
        except:
            self.write_key = ''

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

    def upload(self, filename, path=None, touch=False):
        if not path:
            path = filename

        if touch:
            epoch = time.time()
        else:
            epoch = os.path.getatime(filename)

        size = os.path.getsize(filename)
        deb(f'uploading {filename} {size/1024} kb to server as {path}')
        index = 0
        offset = 0

        if not size:
            response = requests.post('{}/upload/{}'.format(self.server, path),
                                     headers={'key': self.write_key},
                                     data='',
                                     params={'time': epoch},
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
                                             params={'time': epoch},
                                             verify=self.certificate)
                    index = offset
            except Exception as e:
                print(e)

        try:
            if response.status_code == 201:
                return ErrorCode.OK
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
        response = requests.get('{}/filelist/{}'.format(self.server, path),
                                headers={'key': self.write_key},
                                params={'recursive': recursive},
                                verify=self.certificate)
        if pretty:
            return ErrorCode.OK, json.dumps(response.json(), indent=4)
        return ErrorCode.OK, response.json()
