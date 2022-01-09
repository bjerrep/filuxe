import os


def file_is_closed(fqn):
    """
    This method was introduced because a file while being copied was seen to report a timestamp
    of 'now' before getting the final and correct timestamp from the source file.
    This could make the forwarder delete wrong files if it deletes by date (and is configured
    to delete files obviously).

    This method is insanely slow and since the problem seems to have disappeared (perhaps after
    a change to use pyinotify instead of watchdog?) it is just kept for now as a reminder.
    """

    # for proc in psutil.process_iter():
    #     try:
    #         for item in proc.open_files():
    #             if fqn == item.path:
    #                 return False
    #     except:
    #         pass
    #
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
