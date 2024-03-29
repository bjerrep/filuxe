import time, re, os, copy
import requests
from log import deb, inf, war, err, human_file_size, Indent
from errorcodes import ErrorCode
import util


def print_file(item, extra=''):
    datetime = time.strftime("%m/%d/%Y %H:%M:%S", time.gmtime(item.attr["time"]))
    human_size = human_file_size(item.attr["size"])
    deb(f'{extra} - {human_size:<10} {item.attr["time"]:<20} {datetime} "{item.file}"')


def delete_http_file(filuxe_handle, filepath):
    try:
        inf(f'http: deleting {filuxe_handle.log_path(filepath)}')
        filuxe_handle.delete(filepath)
    except requests.ConnectionError:
        war('delete failed, server is not reachable.')


def filename_is_included(filename, rules):
    try:
        if not rules['export']:
            deb(f'export is false for {filename}')
            return False
    except:
        pass

    try:
        include_list = rules['include']
        for include in include_list:
            a = re.search(include, filename)
            if a:
                break
        if not a:
            deb(f'{filename} was not included by "{include}"')
            return False
    except re.error as e:
        err(f'include regex exception, "{include}" gave {e.__repr__()}. File ignored.')
        return False
    except:
        # then default forward everything
        pass

    try:
        exclude_list = rules['exclude']
        for exclude in exclude_list:
            a = re.search(exclude, filename)
            if a:
                deb(f'ignore file hit for {filename}')
                return False
    except re.error as e:
        err(f'exclude regex exception, "{exclude}" gave {e.__repr__()}. File ignored.')
        return False
    except:
        pass

    return True


def filter_filelist(filelist, rules):
    """
    Return a copy of the filelist where not-included and excluded files are removed according to the rule set.
    """
    try:
        filtered_filelist = copy.deepcopy(filelist)

        for path, files in filelist['filelist'].items():
            if not rules['dirs'].get(path):
                # Probably got a directory from a wan filelist that does not exist on lan.
                inf(f'filter filelist: ignoring directory "{path}" which is not found in rules')
            else:
                for filename in files:
                    if not filename_is_included(filename, rules['dirs'][path]):
                        del filtered_filelist['filelist'][path][filename]
    except:
        deb('http filelist returned unfiltered (bad rules?)')

    return filtered_filelist


def get_http_filelist(filuxe_handle, path='/', recursive=True, rules=None):
    """
    Retrieve a filelist of files at path, or starting at path if recursive is True.
    If rules are given then the filelist will be (post) filtered to only contain entries
    covered by the rule set. It would make sense if the filtering were done on the server
    but this is not implemented yet.
    """
    try:
        error_code, filelist = filuxe_handle.list(path, recursive=recursive)
        if error_code != ErrorCode.OK:
            err(f'get http filelist got error {error_code}')
            return None
        if not rules:
            return filelist

        return filter_filelist(filelist, rules)

    except requests.ConnectionError:
        war(f'unable to get file list from {filuxe_handle.domain} over http(s), server unreachable')
    return None


def filestorage_scan(root, path='', recursive=True):
    _filelist = {}
    total_directories = 0
    total_files = 0
    total_size = 0

    scan_root = os.path.join(root, path)

    if recursive:
        inf(f'recursively scanning "{scan_root}"')
    else:
        inf(f'rescanning directory "{scan_root}"')

    with Indent() as _:
        for _root, _dirs, _files in os.walk(scan_root):
            _path = os.path.relpath(_root, scan_root)
            size = 0

            relative_path = os.path.normpath(os.path.join(path, _path))
            if not _filelist.get(relative_path):
                _filelist[relative_path] = {}

            for _file in _files:
                try:
                    file = os.path.join(_root, _file)
                    if util.file_is_closed(os.path.abspath(file)):
                        _size = os.path.getsize(file)
                        epoch = util.get_file_time(file)
                        metrics = {'size': _size, 'time': epoch}
                        _filelist[relative_path][_file] = metrics
                        size += os.path.getsize(os.path.join(_root, _file))
                    else:
                        war(f'filestorage scan, ignoring open file {file}')
                except FileNotFoundError:
                    deb(f'filestorage scan: file not found {file}')

            total_directories += 1
            total_files += len(_files)
            total_size += size

            message = f'scanned "{relative_path}", {human_file_size(size)} in {len(_files)} files'
            if recursive:
                # If recursive it will be the first full scan so print what is happening
                inf(message)
            else:
                deb(message)

            if not recursive:
                break

        inf(f'found {total_directories} directories with {total_files} files occupying {human_file_size(total_size)}')

    return {'filelist': _filelist,
            'info': {'dirs': total_directories, 'fileroot': relative_path, 'files': total_files, 'size': total_size}}


def get_local_filelist(root='/', path='', recursive=True, rules=None):
    """
    """
    filelist = filestorage_scan(root, path, recursive)
    if not rules:
        return filelist

    return filter_filelist(filelist, rules)
