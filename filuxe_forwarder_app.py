import threading
import time

from log import deb, inf, war, err, die, human_file_size, Indent
from errorcodes import ErrorCode
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, DirCreatedEvent
from watchdog.events import FileDeletedEvent
import requests
import filuxe_api
import fwd_util, fwd_file_deleter
import os, copy, signal, json

scan = {}
loaded_rules = None
active_rules = None
observer = None
file_root = None
filuxe_wan = None
filuxe_lan = None
config = None
lan_file_deleter = None
idle_detect = None


def calculate_rules(check_dirs):
    """
    1: check_dirs as list of directories:
    Starting from the root then recursively propagate rules matching the given directory structure.

    2: check_dirs as directory
    This can set rules on a new directory. If the directory already has rules assigned then it is a no-op.
    """
    global loaded_rules, active_rules

    if not loaded_rules:
        active_rules = None
        return

    inf('calculating rules')
    with Indent() as _:

        default_rule = loaded_rules["default"]
        try:
            dir_rules = loaded_rules["dirs"]
            entry_rules_json = json.dumps(dir_rules, sort_keys=True)
        except:
            war('no "dir" rules file section found, using "default" section only')
            return

        if isinstance(check_dirs, list):
            check_dirs.sort()
            new_rules = {}
        else:
            check_dirs = [check_dirs]
            new_rules = copy.deepcopy(active_rules['dirs'])

        try:
            for _key in check_dirs:
                _path_elements = _key.split(os.sep)

                for i in range(len(_path_elements)):
                    path_elements = _path_elements[:i + 1]

                    path = os.path.join(*path_elements)

                    if path == '.':
                        new_rules[path] = default_rule
                    else:
                        previous = os.path.relpath(os.path.join(path, os.pardir))
                        try:
                            new_rules[path] = {**new_rules[previous], **dir_rules[path]}
                        except:
                            try:
                                new_rules[path] = new_rules[previous]
                            except:
                                deb(f'no rules found for {path}, skipped')

                    deb(f'transient rule: "{path}" {new_rules[path]}')
        except:
            war(f'establishing rules for {_key} failes, check rules file')

        # purge rules that doesn't trigger any actions

        new_rules_copy = copy.deepcopy(new_rules)
        active_new_rules = {}
        active_new_rules['dirs'] = {}

        for path, path_rules in new_rules_copy.items():
            if path_rules.get('export') or len(path_rules) > 1:
                inf(f'adding rule for "{path}" : {path_rules}')
                active_new_rules['dirs'][path] = path_rules

        new_rules_json = json.dumps(active_new_rules, sort_keys=True)
        changed = entry_rules_json != new_rules_json

        extras = ''
        if changed:
            active_rules = active_new_rules
            extras = '. Rules were adjusted'
        else:
            extras = '. No changes ?'

    inf(f'rules calculated, {len(active_rules["dirs"])} active rules{extras}')


def dump_rules():
    try:
        if not active_rules['dirs'].items():
            war('this forwarder has no rules loaded ? Forwarding everything.')
        else:
            deb('dumping rules:')
            for _path, _rules in active_rules['dirs'].items():
                deb(f' "{_path}" {_rules}')
    except:
        war('no dir rules found')
        pass


def export_file(filepath):
    """ Use filuxe to upload the file if it first matches the include regex and
        second doesn't match the exclude regex.
        If the include regex and the exclude regex are both empty strings then
        the file is exported.
    """
    if not filuxe_wan:
        return

    path = os.path.dirname(filepath)
    relpath = os.path.relpath(path, file_root)

    file = os.path.basename(filepath)

    try:
        dir_rules = active_rules['dirs'][relpath]
        if not fwd_util.filename_is_included(file, dir_rules):
            inf(f'filename {file} is not in scope and will not be exported')
            return
        deb(f'forwarding {file}')
    except:
        inf(f'from {relpath} uploading file {file} (no rules)')

    try:
        deb(f'uploading {filuxe_lan.log_path(filepath)}')
        filuxe_wan.upload(filepath, os.path.join(relpath, file))
    except requests.ConnectionError:
        war('upload failed, WAN server is not reachable.')
    except FileNotFoundError:
        war(f'exception file not found, {os.path.join(relpath, file)} (internal race)')


def delete_wan_file(filepath):
    """
    Delete file on WAN if WAN is configured. This will be triggered when a file is
    deleted from LAN filestorage.
    """
    if not filuxe_wan:
        return

    path = os.path.dirname(filepath)

    try:
        if not active_rules['dirs'][path]['delete']:
            deb(f'not deleting on wan since delete=false for {filepath}')
            return
    except:
        pass

    try:
        file = os.path.basename(filepath)
        relpath = os.path.normpath(path)
        dir_rules = active_rules['dirs'][relpath]
        if not fwd_util.filename_is_included(file, dir_rules):
            inf(f'filename {file} is not in scope and will not be exported')
            return
    except:
        deb(f'from "{filuxe_wan.log_path(relpath)}" deleting file {file} (no rules)')

    fwd_util.delete_http_file(filuxe_wan, filepath)


def print_file_list(files, title=None):
    if title == '':
        title = '/'
    if title:
        deb(f'filelist for "{title}"')
    for item in files.items():
        fwd_util.print_file(item)


class IdleDetect(threading.Thread):
    """
    Initially made to facilitate testing with pexpect but now its just nice
    to have as a log separator whenever the forwarder seems to be idle.
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.timeout = 2
        self.daemon = True
        self.start()

    def activity(self):
        self.timeout = 2

    def run(self):
        while True:
            time.sleep(1)
            if self.timeout >= 0:
                self.timeout -= 1
                if self.timeout == -1:
                    inf('idle')


class Listener(FileSystemEventHandler):
    def on_any_event(self, event):
        idle_detect.activity()

    def new_file(self, filename):
        if not os.path.exists(filename):
            deb(f'listener: changed file "{filename}" does not exist anymore?')
            return

        inf(f'listener: new/changed file "{filuxe_lan.log_path(filename)}"')

        with Indent() as _:
            path = os.path.dirname(filename)
            filestorage_path = os.path.relpath(path, filuxe_lan.root())
            lan_file_deleter.enforce_max_files(filestorage_path)
            if not os.path.exists(filename):
                war(f'listener: new file "{filuxe_lan.log_path(filename)}" already deleted and will not be forwarded')
                return
            export_file(filename)

    def on_closed(self, event):
        self.new_file(event.src_path)

    def on_created(self, event):
        if isinstance(event, DirCreatedEvent):
            src_path = os.path.relpath(event.src_path, file_root)
            inf(f'listener: new dir {src_path}')
            calculate_rules(src_path)

    def on_deleted(self, event):
        path = os.path.relpath(event.src_path, file_root)
        inf(f'listener: file was deleted: {filuxe_lan.log_path(event.src_path)}"')
        with Indent() as _:
            if filuxe_wan:
                if isinstance(event, FileDeletedEvent):
                    delete_wan_file(path)
                else:
                    inf(f'listener: deleted directory "{path}" (no action)')


def run_filesystem_observer(root):
    global observer
    inf(f'starting file observer in {root}')
    observer = Observer()
    listener = Listener()
    observer.schedule(listener, root, recursive=True)
    observer.start()
    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)


def coldstart_rules():
    dirs = fwd_util.filestorage_directory_scan(file_root)
    calculate_rules(dirs)
    dump_rules()


def terminate(_, __):
    observer.stop()


def synchonize(cfg):
    inf('synchonizing with WAN server, please wait')

    with Indent() as _:
        # at its core then lan here just mean 'the local filesystem'.
        lan_files = fwd_util.get_local_filelist(filuxe_lan.root())

        # If the WAN server is missing then the forwarder will not be able to do its job before
        # the WAN server can be reached.
        wan_files = fwd_util.get_http_filelist(filuxe_wan, rules=active_rules)

        if lan_files is None or wan_files is None:
            war('retrieving filelists failed, synchonization aborted')
            return

        inf(f'found {lan_files["info"]["files"]} files on LAN server and {wan_files["info"]["files"]} on WAN server')

        new_files = []
        modified_files = []
        copy_bytes = 0
        for directory, filelist in lan_files['filelist'].items():
            if directory not in wan_files['filelist']:
                for filename, metrics in lan_files['filelist'][directory].items():
                    pathname = os.path.join(directory, filename)
                    new_files.append(pathname)
                    copy_bytes += metrics['size']
                continue

            for filename, metrics in filelist.items():
                pathname = os.path.join(directory, filename)
                if filename not in wan_files['filelist'][directory]:
                    new_files.append(pathname)
                    copy_bytes += metrics['size']
                elif metrics['time'] != wan_files['filelist'][directory][filename]['time']:
                    modified_files.append(pathname)
                    copy_bytes += metrics['size']

        if not len(new_files) + len(modified_files):
            inf('WAN server is up-to-date')
        else:
            inf(f'synchonizing: uploading {human_file_size(copy_bytes)} in {len(new_files)} new files '
                f'and {len(modified_files)} modified files')
            for file in new_files + modified_files:
                export_file(os.path.join(file_root, file))
            inf('synchonizing: complete')


def generate_default_rules():
    return None


def start(args, cfg, _rules):
    global loaded_rules, file_root, filuxe_wan, filuxe_lan, config, lan_file_deleter, idle_detect

    file_root = cfg['lan_filestorage']
    inf('filestorage root %s' % file_root)

    config = cfg
    if _rules:
        loaded_rules = _rules
        coldstart_rules()
    else:
        loaded_rules = generate_default_rules()
        war('running with default rules, forwarding everything')

    try:
        filuxe_wan = filuxe_api.Filuxe(config, lan=False, force=True)
    except:
        war('no wan configuration found, forwarding disabled')

    if filuxe_wan:
        try:
            error, stats = filuxe_wan.get_stats()
            inf(f'connected to wan server version {stats["version"]}')
        except:
            err('wan server unreachable, forwarding disabled')
            filuxe_wan = None

    try:
        filuxe_lan = filuxe_api.Filuxe(config, lan=True)
    except:
        die('no lan configuration found, can\'t continue')

    try:
        error, stats = filuxe_lan.get_stats()
        inf(f'connected to lan server version {stats["version"]}')
    except requests.exceptions.ConnectionError:
        war('lan server unreachable, continuing anyway')
    except Exception as e:
        die('unexpected exception while contacting lan server', e)

    try:
        if filuxe_wan and cfg['sync_at_startup']:
            synchonize(cfg)
    except:
        inf('syncronizing lan to wan failed')

    lan_file_deleter = fwd_file_deleter.FileDeleter(filuxe_lan, active_rules, args.dryrun)
    lan_file_deleter.enforce_max_files('', recursive=True)

    idle_detect = IdleDetect()
    try:
        run_filesystem_observer(file_root)
    except Exception as e:
        die(f'unable to start file observer in {file_root}', e)

    inf('filuxe forwarder is ready')

    try:
        observer.join()
    except Exception as e:
        die('the fileobserver crashed. Perhaps the filestorage was deleted ?', e)
    return ErrorCode.OK
