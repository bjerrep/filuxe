from log import deb, inf, war
from errorcodes import ErrorCode
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileDeletedEvent, FileModifiedEvent
import requests
import filuxe_api
import fwd_util, fwd_file_deleter
import os, copy, re, signal

scan = {}
rules = None
observer = None
file_root = None
filuxe_wan = None
filuxe_lan = None
config = None
file_deleter = None


def filestorage_scan(file_root):
    scan = []
    inf(f'scanning "{file_root}"')
    for root, dirs, files in os.walk(file_root):
        path = os.path.relpath(root, file_root)
        scan.append(path)
        deb(f' - {path}')
    return scan


def calculate_rules(check_dirs=None):
    global rules

    default = rules["default"]
    try:
        dirs = rules["dirs"]
    except:
        war('no "dir" rules file section found, using "default" section only')
        return

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
    try:
        deb('Dumping rules:')
        for _path, _rules in rules['dirs'].items():
            deb(f' - {_path} {_rules}')
    except:
        inf('- no dir rules found')
        pass


def export_file(filepath):
    """ Use filuxe to upload the file if it first matches the include regex and
        second doesn't match the exclude regex.
        A small side-note: If the include regex and the exclude regex are both
        empty strings the file is exported.
    """
    if not filuxe_wan:
        return

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
    except FileNotFoundError:
        war(f'exception file not found, {os.path.join(relpath, file)} (internal race)')


def delete_wan_file(filepath):
    """
    If "delete" is true then files deleted locally on the lan storage will be deleted on
    the wan filestorage as well.
    """
    if not filuxe_wan:
        return

    path = os.path.dirname(filepath)

    try:
        if not rules['dirs'][path]['delete']:
            deb(f'not deleting on wan since delete=false for {filepath}')
            return
    except:
        pass

    fwd_util.delete_file(filepath, filuxe_wan)


def print_file_list(files, title=None):
    if title == '':
        title = '/'
    if title:
        deb(f'filelist for "{title}"')
    for item in files.items():
        fwd_util.print_file(item)


class Listener(FileSystemEventHandler):
    def on_any_event(self, event):
        print(event)

    def on_created(self, event):
        src_path = os.path.relpath(event.src_path, file_root)
        if isinstance(event, FileCreatedEvent):
            inf(f'new file {src_path}')
        else:
            inf(f'new dir {src_path}')

    def on_modified(self, event):
        src_path = os.path.relpath(event.src_path, file_root)
        path = os.path.dirname(src_path)
        if isinstance(event, FileModifiedEvent):
            inf(f'changed file {os.path.basename(src_path)} as {src_path}')
            calculate_rules([path, ])
            export_file(event.src_path)
            file_deleter.enforce_max_files(filuxe_lan, path)
        else:
            inf(f'new directory {src_path} (no action)')
            calculate_rules([src_path, ])

    def on_deleted(self, event):
        if filuxe_wan:
            path = os.path.relpath(event.src_path, file_root)
            if isinstance(event, FileDeletedEvent):
                inf(f'deleted file {path} as {event.src_path}')
                delete_wan_file(path)
            else:
                inf(f'deleted directory {path} (no action)')


def run_filesystem_observer(root):
    global observer
    deb(f'starting file observer in {root}')
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
    lan_files = fwd_util.get_filelist(filuxe_lan)

    # If the WAN server is missing then the forwarder will not be able to do its job before
    # the WAN server can be reached.
    wan_files = fwd_util.get_filelist(filuxe_wan)

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
    global rules, file_root, filuxe_wan, filuxe_lan, config, file_deleter
    config = cfg
    if _rules:
        rules = _rules
    else:
        rules = generate_default_rules()

    file_deleter = fwd_file_deleter.FileDeleter(rules, args.dryrun)

    file_root = cfg['lan_filestorage']
    inf('filestorage root %s' % file_root)

    try:
        filuxe_wan = filuxe_api.Filuxe(config, lan=False, force=True)
    except:
        war('failed loading or starting wan connection, wan disabled')
        filuxe_wan = None
    filuxe_lan = filuxe_api.Filuxe(config, lan=True)

    coldstart_rules()

    try:
        if cfg['sync_at_startup']:
            synchonize(cfg)
    except:
        inf('not syncronizing, "sync_at_startup" not enabled')

    run_filesystem_observer(file_root)

    file_deleter.enforce_max_files(filuxe_lan, '', recursive=True)
    print('filuxe forwarder is ready')
    observer.join()
    return ErrorCode.OK
