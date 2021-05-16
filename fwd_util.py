from log import deb, inf, war
import requests
import time


def print_file(item):
    datetime = time.strftime("%m/%d/%Y %H:%M:%S", time.gmtime(item.attr["time"]))
    deb(f' - {item.file:<20} {item.attr["size"]:<10} {item.attr["time"]:<20} {datetime}')


def delete_file(filepath, filuxe_handle):
    inf(f'deleting "{filepath}"')
    try:
        filuxe_handle.delete(filepath)
    except requests.ConnectionError:
        war('delete failed, server is not reachable.')


def get_filelist(filuxe_handle, path='/', recursive=True):
    try:
        errorcode, filelist = filuxe_handle.list(path, recursive=recursive)
        return filelist
    except requests.ConnectionError:
        war(f'unable to get file list from {filuxe_handle.domain}, server unreachable')
    return None
