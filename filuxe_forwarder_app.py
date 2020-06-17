from log import deb, inf, war
from errorcodes import ErrorCode
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileDeletedEvent
import requests
import filuxe_api
import os, copy, re, signal, time

scan = {}
rules = None
observer = None
file_root = None
filuxe_wan = None
filuxe_lan = None
config = None


def filestorage_scan(file_root):
    scan = []
    inf(f'scanning {file_root}')
    for root, dirs, files in os.walk(file_root):
        path = os.path.relpath(root, file_root)
        scan.append(path)
        deb(f' - {path}')
    return scan


def get_files(filuxe_handle, path='/', recursive=True):
    try:
        errorcode, lan_list = filuxe_handle.list(path, recursive=recursive)
        lan_files = lan_list['files']
        deb(lan_files)
        return lan_files
    except requests.ConnectionError:
        war(f'unable to get file list from {filuxe_handle.domain}, server unreachable')
    return None


def calculate_rules(check_dirs=None):
    global rules
    dirs = rules["dirs"]
    default = rules["default"]

    if check_dirs:
        inf('recalculating rules from filesystem')
        check_dirs.sort()
        keys = check_dirs
    else:
        inf('recalculating rules from config file')
        keys = list(dirs.keys())

    for key in keys:
        elements = key.split(os.sep)
        try:
            existing = dirs[key]
        except:
            existing = None
        if len(elements) == 1:
            try:
                dirs[key] = {**default, **dirs[key]}
            except:
                dirs[key] = default
        else:
            previous = os.path.relpath(os.path.join(key, os.pardir))
            try:
                dirs[key] = {**dirs[previous], **dirs[key]}
            except:
                # Adding a path where inheriting settings from the parent path fails
                # since there is no entry for the parent path to be found.
                # Manually traverse the path and inherit settings for all new entries.
                previous = None
                for i in range(len(elements)):
                    current = '/'.join(elements[:i + 1])
                    try:
                        if current not in dirs:
                            dirs[current] = copy.deepcopy(dirs[previous])
                    except:
                        dirs[current] = copy.deepcopy(default)
                    previous = current

        if not existing or existing != dirs[key]:
            deb(f'rule: {key} {dirs[key]}')
    deb(f'{len(rules["dirs"])} rules')


def dump_rules():
    deb('Dumping rules:')
    for _path, _rules in rules['dirs'].items():
        deb(f' - {_path} {_rules}')


def export_file(filepath):
    """ Use filuxe to upload the file if it first matches the include regex and
        second doesn't match the exclude regex.
        A small side-note: If the include regex and the exclude regex are both
        empty strings the file is exported.
    """

    path = os.path.dirname(filepath)
    relpath = os.path.relpath(path, file_root)

    try:
        if not rules['dirs'][relpath]['export']:
            deb(f'export=false for {filepath}')
            return
    except:
        pass

    file = os.path.basename(filepath)
    rule = rules['dirs'][relpath]
    try:
        include = rule['include']
        a = re.search(include, file)
        if not a:
            deb(f'{file} was not included by "{include}"')
            return
    except:
        pass

    try:
        exclude = rule['exclude']
        a = re.search(exclude, file)
        if a:
            deb(f'{file} was excluded by "{exclude}"')
            return
    except:
        pass

    deb(f'forwarding {file}')
    try:
        filuxe_wan.upload(filepath, os.path.join(relpath, file))
    except requests.ConnectionError:
        war('upload failed, WAN server is not reachable.')


def print_file(item):
    datetime = time.strftime("%m/%d/%Y %H:%M:%S", time.gmtime(item.attr["time"]))
    deb(f' - {item.file:<20} {item.attr["size"]:<10} {item.attr["time"]:<20} {datetime}')


def print_file_list(files, title=None):
    if title == '':
        title = '/'
    if title:
        deb(f'filelist for "{title}"')
    for item in files.items():
        print_file(item)


def delete_file(filepath, filuxe_handle):
    file = os.path.basename(filepath)
    inf(f'deleting {file}')
    try:
        filuxe_handle.delete(filepath)
    except requests.ConnectionError:
        war('delete failed, server is not reachable.')


def enforce_max_files(path):
    try:
        max_files = rules['dirs'][path]['max_files']
    except:
        deb('no file limit')
        return
    if max_files < 0:
        return

    try:
        delete_by = rules['dirs'][path]['delete_by']
    except:
        delete_by = 'time'

    class Item:
        def __init__(self, x):
            self.file = x[0]
            self.attr = x[1]
            self.numbers = None
            if delete_by == 'version':
                try:
                    p = re.compile(rules['dirs'][path]['version'])
                    self.numbers = [int(x) for x in p.search(self.file).group(1).split('.')]
                    if len(self.numbers) != 3:
                        self.numbers = None
                        war(f'failed to parse version from {self.file}')
                except:
                    pass

            self.time = x[1]['time']

        def __lt__(self, other):
            if self.numbers and other.numbers:
                if self.numbers[0] < other.numbers[0]:
                    return True
                if self.numbers[0] > other.numbers[0]:
                    return False
                if self.numbers[1] < other.numbers[1]:
                    return True
                if self.numbers[1] > other.numbers[1]:
                    return False
                return self.numbers[2] < other.numbers[2]

            return self.time < other.time

    for domain in (filuxe_lan, filuxe_wan):
        files = get_files(domain, path, recursive=False)
        to_delete = len(files) - max_files
        if to_delete > 0:
            inf(f'deleting {to_delete} files from {domain.domain} filestorage')
            _items = [Item(x) for x in files.items()]
            _sorted_items = sorted(_items)

            for item in _sorted_items:
                print_file(item)
            for item in _sorted_items[:to_delete]:
                delete_file(item.file, domain)


class Listener(FileSystemEventHandler):
    def on_any_event(self, event):
        print(event)

    def on_created(self, event):
        src_path = os.path.relpath(event.src_path, file_root)
        path = os.path.dirname(src_path)
        if isinstance(event, FileCreatedEvent):
            inf(f'new file {os.path.basename(src_path)} as {src_path}')
            calculate_rules([path, ])
            export_file(event.src_path)
            enforce_max_files(path)
        else:
            inf(f'new directory {src_path} (no action)')
            calculate_rules([src_path, ])

    def on_deleted(self, event):
        path = os.path.relpath(event.src_path, file_root)
        if isinstance(event, FileDeletedEvent):
            inf(f'deleted file {path} as {event.src_path}')
            delete_file(path, filuxe_wan)
        else:
            inf(f'deleted directory {path} (no action)')


def run_filesystem_observer(root):
    global observer
    observer = Observer()
    listener = Listener()
    observer.schedule(listener, root, recursive=True)
    observer.start()
    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)


def coldstart_rules():
    calculate_rules()
    dirs = filestorage_scan(file_root)
    calculate_rules(dirs)
    dump_rules()


def terminate(_, __):
    observer.stop()


def synchonize(cfg):
    inf('synchonizing with WAN server, please wait')

    # If the LAN server is missing then for the forwarder it just means that the initial
    # synchronisation will fail. The LAN server is not used by the forwarder otherwise.
    lan_files = get_files(filuxe_lan)

    # If the WAN server is missing then the forwarder will not be able to do its job before
    # the WAN server can be reached.
    wan_files = get_files(filuxe_wan)

    if lan_files is None or wan_files is None:
        war('synchonization aborted')
        return

    inf(f'found {len(lan_files)} files on LAN server and {len(wan_files)} on WAN server')

    new_files = []
    modified_files = []
    copy_bytes = 0
    for key, val in lan_files.items():
        if key not in wan_files:
            new_files.append(key)
            copy_bytes += val['size']
        elif val['time'] != wan_files[key]['time']:
            modified_files.append(key)
            copy_bytes += val['size']

    if not len(new_files) + len(modified_files):
        inf('WAN server is up-to-date')
    else:
        inf(f'synchonizing: found {copy_bytes} bytes in {len(new_files)} new files '
            f'and {len(modified_files)} modified files')
        for file in new_files + modified_files:
            export_file(os.path.join(file_root, file))
        inf('synchonizing: complete')


def generate_default_rules():
    return {"default": {}, "dirs": {}}


def start(args, cfg, _rules):
    global rules, file_root, filuxe_wan, filuxe_lan, config
    config = cfg
    if _rules:
        rules = _rules
    else:
        rules = generate_default_rules()

    file_root = cfg['lan_filestorage']
    inf('filestorage root %s' % file_root)

    filuxe_wan = filuxe_api.Filuxe(config, lan=False)
    filuxe_lan = filuxe_api.Filuxe(config, lan=True)

    coldstart_rules()

    try:
        if cfg['sync_at_startup']:
            synchonize(cfg)
    except:
        inf('not syncronizing, "sync_at_startup" not enabled')

    run_filesystem_observer(file_root)
    print('filuxe forwarder is ready')
    observer.join()
    return ErrorCode.OK
