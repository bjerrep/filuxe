import os, copy, signal, json, threading, time
import asyncio, pyinotify
import requests
from log import deb, inf, war, err, die, human_file_size, Indent
from errorcodes import ErrorCode
import filuxe_api
import fwd_util, fwd_file_deleter


scan = {}
LOADED_RULES = None
ACTIVE_RULES = None
LOOP = None
WATCH_MANAGER = None
FILE_ROOT = None
FILUXE_WAN = None
FILUXE_LAN = None
CONFIG = None
LAN_FILE_DELETER = None
IDLE_DETECT = None


def calculate_rules(check_dirs):
    """
    1: check_dirs as list of directories:
    Starting from the root then recursively propagate rules matching the given directory structure.

    2: check_dirs as directory
    This can set rules on a new directory. If the directory already has rules assigned then it is a no-op.
    """
    global LOADED_RULES, ACTIVE_RULES

    if not LOADED_RULES:
        ACTIVE_RULES = None
        return

    inf('calculating rules')
    with Indent() as _:

        default_rule = LOADED_RULES["default"]
        try:
            dir_rules = LOADED_RULES["dirs"]
            entry_rules_json = json.dumps(dir_rules, sort_keys=True)
        except:
            war('no "dir" rules file section found, using "default" section only')
            return

        if isinstance(check_dirs, list):
            check_dirs.sort()
            new_rules = {}
        else:
            check_dirs = [check_dirs]
            new_rules = copy.deepcopy(ACTIVE_RULES['dirs'])

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
            war(f'establishing rules for {_key} failed, check rules file')

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

        if changed:
            ACTIVE_RULES = active_new_rules
            extras = '. Rules were adjusted'
        else:
            extras = '. No changes ?'

    inf(f'rules calculated, {len(ACTIVE_RULES["dirs"])} active rules{extras}')


def dump_rules():
    try:
        if not ACTIVE_RULES['dirs'].items():
            war('this forwarder has no rules loaded ? Forwarding everything.')
        else:
            deb('dumping rules:')
            for _path, _rules in ACTIVE_RULES['dirs'].items():
                deb(f' "{_path}" {_rules}')
    except:
        war('no dir rules found')


def export_file(filepath):
    """ Use filuxe to upload the file if it first matches the include regex and
        second doesn't match the exclude regex.
        If the include regex and the exclude regex are both empty strings then
        the file is exported.
    """
    if not FILUXE_WAN:
        return

    path = os.path.dirname(filepath)
    relpath = os.path.relpath(path, FILE_ROOT)

    file = os.path.basename(filepath)

    try:
        dir_rules = ACTIVE_RULES['dirs'][relpath]
        if not fwd_util.filename_is_included(file, dir_rules):
            inf(f'filename {file} is not in scope and will not be exported')
            return
        deb(f'forwarding {file}')
    except:
        inf(f'from {relpath} uploading file {file} (no rules)')

    try:
        deb(f'uploading {FILUXE_LAN.log_path(filepath)}')
        FILUXE_WAN.upload(filepath, os.path.join(relpath, file))
    except requests.ConnectionError:
        war('upload failed, WAN server is not reachable.')
    except FileNotFoundError:
        war(f'exception file not found, {os.path.join(relpath, file)} (internal race)')


def delete_wan_file(filepath):
    """
    Delete file on WAN if WAN is configured. This will be triggered when a file is
    deleted from LAN filestorage.
    """
    if not FILUXE_WAN:
        deb(f'no wan configured, not deleting {filepath} on wan')
        return

    filestorage_path = os.path.relpath(filepath, FILUXE_LAN.root())
    path = os.path.dirname(filestorage_path)

    try:
        if not ACTIVE_RULES['dirs'][path]['delete']:
            deb(f'not deleting on wan since delete=false for {filepath}')
            return
    except:
        pass

    try:
        file = os.path.basename(filepath)
        rule_path = os.path.normpath(path)
        dir_rules = ACTIVE_RULES['dirs'][rule_path]
        if not fwd_util.filename_is_included(file, dir_rules):
            inf(f'filename {file} is not in scope and will not be exported')
            return
    except:
        deb(f'from "{FILUXE_WAN.log_path(filepath)}" deleting file {file} (no rules)')

    fwd_util.delete_http_file(FILUXE_WAN, filestorage_path)


def print_file_list(files, title=None):
    if title == '':
        title = '/'
    if title:
        deb(f'filelist for "{title}"')
    for item in files.items():
        fwd_util.print_file(item)


def new_file(filename):
    if not os.path.exists(filename):
        deb(f'listener: changed file "{filename}" does not exist anymore?')
        return

    inf(f'listener: new/changed file "{FILUXE_LAN.log_path(filename)}"')

    with Indent() as _:
        if LAN_FILE_DELETER:
            path = os.path.dirname(filename)
            filestorage_path = os.path.relpath(path, FILUXE_LAN.root())
            LAN_FILE_DELETER.enforce_max_files(filestorage_path, rules=LOADED_RULES, recursive=False)

        if not os.path.exists(filename):
            war(f'listener: new file "{FILUXE_LAN.log_path(filename)}" already deleted and will not be forwarded')
            return

        export_file(filename)


class IdleDetect(threading.Thread):
    """
    Initially made to facilitate testing with pexpect but now its just nice
    to have as a log separator whenever the forwarder seems to be idle.
    """
    def __init__(self):
        threading.Thread.__init__(self)
        self.modified_files = {}
        self.idle_timeout = 3
        self.timeout = self.idle_timeout
        self.daemon = True
        self.start()

    def activity(self):
        self.timeout = self.idle_timeout

    def run(self):
        while True:
            time.sleep(1)
            if self.timeout:
                self.timeout -= 1
                if not self.timeout:
                    inf('idle')


class EventHandler(pyinotify.ProcessEvent):
    def process_default(self, event):
        print(event)

    def process_IN_CLOSE_WRITE(self, event):
        deb(f'inotify: closed {event.pathname}')
        new_file(event.pathname)
        IDLE_DETECT.activity()

    def process_IN_DELETE(self, event):
        deb(f'inotify: delete {event.pathname}')
        delete_wan_file(event.pathname)
        IDLE_DETECT.activity()

    def process_IN_MOVED_FROM(self, event):
        deb(f'inotify: move(delete) {event.pathname}')
        delete_wan_file(event.pathname)
        IDLE_DETECT.activity()

    def process_IN_MOVED_TO(self, event):
        deb(f'inotify: move(write) {event.pathname}')
        new_file(event.pathname)
        IDLE_DETECT.activity()

    def process_IN_CREATE(self, event):
        if event.dir:
            inf(f'new directory "{FILUXE_LAN.log_path(event.pathname)}"')
            path = os.path.relpath(event.pathname, FILUXE_LAN.root())
            calculate_rules(path)
        else:
            inf(f'new file "{FILUXE_LAN.log_path(event.pathname)}"')
            new_file(event.pathname)


def run_filesystem_observer(root):
    global LOOP, WATCH_MANAGER
    inf(f'starting file observer in {root}')

    LOOP = asyncio.get_event_loop()
    WATCH_MANAGER = pyinotify.WatchManager()
    pyinotify.AsyncioNotifier(WATCH_MANAGER, LOOP, default_proc_fun=EventHandler())
    mask = pyinotify.IN_CLOSE_WRITE | pyinotify.IN_DELETE | pyinotify.IN_MOVED_FROM | pyinotify.IN_MOVED_TO
    WATCH_MANAGER.add_watch(root, mask, rec=True, auto_add=True)

    signal.signal(signal.SIGINT, terminate)
    signal.signal(signal.SIGTERM, terminate)


def coldstart_rules(lan_files):
    dirs = list(lan_files['filelist'].keys())
    calculate_rules(dirs)
    dump_rules()


def terminate(_, __):
    LOOP.call_soon_threadsafe(LOOP.stop)


def synchonize(lan_files):
    inf('synchonizing with WAN server, please wait')

    with Indent() as _:
        # If the WAN server is missing then the forwarder will not be able to do its job before
        # the WAN server can be reached.
        wan_files = fwd_util.get_http_filelist(FILUXE_WAN, rules=ACTIVE_RULES)

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
                export_file(os.path.join(FILE_ROOT, file))
            inf('synchonizing: complete')


def start(args, cfg, rules):
    global LOADED_RULES, FILE_ROOT, FILUXE_WAN, FILUXE_LAN, CONFIG, LAN_FILE_DELETER, IDLE_DETECT
    lan_files = None

    FILE_ROOT = cfg['lan_filestorage']

    if not os.path.exists(FILE_ROOT):
        die(f'filestorage root {FILE_ROOT} not found. Giving up')

    inf(f'filestorage root {FILE_ROOT}')

    CONFIG = cfg
    if rules:
        LOADED_RULES = rules
        lan_files = fwd_util.get_local_filelist(FILE_ROOT)
        coldstart_rules(lan_files)
    else:
        war('running with default rules, forwarding everything')

    try:
        FILUXE_WAN = filuxe_api.Filuxe(CONFIG, lan=False, force=True)
    except:
        war('no wan configuration found, forwarding disabled')

    if FILUXE_WAN:
        try:
            _, stats = FILUXE_WAN.get_stats()
            inf(f'connected to wan server version {stats["version"]}')
        except:
            err('wan server unreachable, forwarding disabled')
            FILUXE_WAN = None

    try:
        FILUXE_LAN = filuxe_api.Filuxe(CONFIG, lan=True)
    except:
        die('no lan configuration found, can\'t continue')

    try:
        _, stats = FILUXE_LAN.get_stats()
        inf(f'connected to lan server version {stats["version"]}')
    except requests.exceptions.ConnectionError:
        war('lan server unreachable, continuing anyway')
    except Exception as e:
        die('unexpected exception while contacting lan server', e)

    if ACTIVE_RULES:
        LAN_FILE_DELETER = fwd_file_deleter.FileDeleter(FILUXE_LAN, args.dryrun)
        LAN_FILE_DELETER.enforce_max_files('', rules=ACTIVE_RULES, recursive=True, lan_files=lan_files)

    try:
        if FILUXE_WAN and cfg['sync_at_startup']:
            if not lan_files:
                lan_files = fwd_util.get_local_filelist(FILE_ROOT)
            synchonize(lan_files)
    except Exception as e:
        err(f'syncronizing lan to wan failed {e}')

    IDLE_DETECT = IdleDetect()
    try:
        run_filesystem_observer(FILE_ROOT)
    except Exception as e:
        die(f'unable to start file observer in {FILE_ROOT}', e)

    inf('filuxe forwarder is ready')

    try:
        LOOP.run_forever()
    except Exception as e:
        die('the fileobserver crashed. Perhaps the filestorage was deleted ?', e)

    return ErrorCode.OK
