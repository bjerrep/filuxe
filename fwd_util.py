import copy

from log import deb, inf, war, err, human_file_size, Indent
from errorcodes import ErrorCode
import util
import requests
import time, re, os

last_http_filelist = None


def print_file(item):
    datetime = time.strftime("%m/%d/%Y %H:%M:%S", time.gmtime(item.attr["time"]))
    human_size = human_file_size(item.attr["size"])
    deb(f' - {human_size:<10} {item.attr["time"]:<20} {datetime} "{item.file}"')


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


def filter_filelist(filelist, rules, recursive):
    global last_http_filelist
    try:
        filtered_filelist = copy.deepcopy(filelist)

        for path, files in filelist['filelist'].items():
            for filename, attributes in files.items():
                if not filename_is_included(filename, rules['dirs'][path]):
                    try:
                        if not last_http_filelist['filelist'][path].get(filename):
                            inf(f'ignoring new file "{path}/{filename}", no rules hit')
                    except:
                        pass
                    del filtered_filelist['filelist'][path][filename]
    except:
        deb('http filelist returned unfiltered (bad rules?)')

    if recursive:
        last_http_filelist = copy.deepcopy(filelist)
    else:
        last_http_filelist['filelist'][path] = copy.deepcopy(filelist['filelist'][path])

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

        return filter_filelist(filelist, rules, recursive)

    except requests.ConnectionError:
        war(f'unable to get file list from {filuxe_handle.domain} over http(s), server unreachable')
    return None


def filestorage_scan(file_root):
    _filelist = {}
    total_directories = 0
    total_files = 0
    total_size = 0

    inf(f'scanning "{file_root}"')

    with Indent() as _:
        for root, dirs, files in os.walk(file_root):
            path = os.path.relpath(root, file_root)
            size = 0

            for _file in files:
                if not _filelist.get(path):
                    _filelist[path] = {}

                file = os.path.join(root, _file)
                if util.file_is_closed(file):
                    _size = os.path.getsize(file)
                    epoch = util.get_file_time(file)
                    metrics = {'size': _size, 'time': epoch}
                    _filelist[path][_file] = metrics
                    size += os.path.getsize(os.path.join(root, _file))
                else:
                    war(f'filestorage scan, ignoring open file {file}')

            total_directories += 1
            total_files += len(files)
            total_size += size
            deb(f'scanned "{path}", {human_file_size(size)} in {len(files)} files')

        inf(f'found {total_directories} directories with {total_files} files occupying {human_file_size(total_size)}')

    return {'filelist': _filelist,
            'info': {'dirs': total_directories, 'fileroot': file_root, 'files': total_files, 'size': total_size}}


def filestorage_directory_scan(path):
    return list(filestorage_scan(path)['filelist'].keys())


def get_local_filelist(path='/', recursive=True, rules=None):
    """
    """
    filelist = filestorage_scan(path)
    if not rules:
        return filelist

    return filter_filelist(filelist, rules, recursive)
