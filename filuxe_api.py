import requests, time, os
from log import deb, inf, war, err, die, human_file_size
from errorcodes import ErrorCode
from util import chunked_reader, get_file_time
import config_util
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
                    self.file_root = ''

        except KeyError as e:
            err(f'expected a {e} entry in the configuration file', ErrorCode.MISSING_KEY)

        try:
            self.write_key = cfg['write_key']
        except:
            self.write_key = ''

    def log_path(self, path):
        relpath = os.path.relpath(os.path.abspath(path), self.root())
        return f'[{os.path.normpath(os.path.join(self.domain, relpath))}]'

    def root(self):
        return self.file_root

    @staticmethod
    def load_config_file(filename):
        config_util.load_config(filename)

    def get_stats(self):
        url = f'{self.server}/stats'
        deb(f'getting stats at {url}')
        response = requests.get(url,
                                verify=self.certificate)
        if response.status_code != 200:
            err(f'got {response.status_code} from {self.domain} server at /stats')
            return ErrorCode.SERVER_ERROR, []
        return ErrorCode.OK, json.loads(response.text)

    def download(self, filename, path, force=False):
        url = f'{self.server}/download/{path}'
        response = requests.get(url,
                                verify=self.certificate)
        if response.status_code != 200:
            err(f'server returned error {response.status_code} for downloading "{path}"')
            return ErrorCode.FILE_NOT_FOUND

        if force or not os.path.exists(filename):
            open(filename, 'wb').write(response.content)
            inf(f'downloaded {url} ({human_file_size(os.path.getsize(filename))}) as "{filename}"')
        else:
            die(f'local file "{filename}" already exists, bailing out (see --force)', ErrorCode.FILE_ALREADY_EXIST)
        return ErrorCode.OK

    def upload(self, filename, path=None, touch=False, force=False):
        if not path:
            path = filename

        if not os.path.exists(filename):
            err(f'upload failed, file not found "{filename}"')
            return ErrorCode.FILE_NOT_FOUND

        if touch:
            epoch = time.time()
        else:
            epoch = get_file_time(filename)

        if self.force:
            force = True

        size = os.path.getsize(filename)
        inf(f'uploading "{os.path.normpath(filename)}" ({human_file_size(size)}) to {self.domain} server as "{path}"')
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
                war(f'upload failed with {e}')

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
