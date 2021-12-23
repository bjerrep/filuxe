import psutil, os


def file_is_closed(fqn):
    """
    Before returning files as existing at all then make sure it is closed.
    One problem observed is that a file while being copied can report a
    timestamp of 'now'. This will make the forwarder delete wrong files
    if it deletes by date (and is configured to delete files obviously)
    """
    for proc in psutil.process_iter():
        try:
            for item in proc.open_files():
                if fqn == item.path:
                    return False
        except:
            pass

    return True


def get_file_time(pathname):
    return os.path.getmtime(pathname)


def chunked_reader(filename):
    """
    Notice that this returns None for an empty file
    """
    with open(filename, 'rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            yield chunk
