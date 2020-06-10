

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
