# This is a minimal logging module without external dependencies as if that was a quality
# in itself. Otherwise check out 'coloredlogs' which is the real thing.
#
import logging, sys, traceback, os
from errorcodes import ErrorCode

_indent = ''


class Indent():
    def __init__(self):
        global _indent
        _indent += '   '

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        global _indent
        _indent = _indent[:-3]


RESET = '\033[0m'
add_timestamp = True

handler = logging.StreamHandler(sys.stdout)
if add_timestamp:
    formatter = logging.Formatter(f'%(asctime)s %(levelname)s %(message)s{RESET}', datefmt='%Y-%m-%d %H:%M:%S')
else:
    formatter = logging.Formatter(f'%(levelname)s %(message)s{RESET}')
handler.setFormatter(formatter)
logger = logging.getLogger()
logger.addHandler(handler)
logger.setLevel(logging.INFO)

if True:
    # enable coloring
    GREY = '\033[0;37m'
    WHITE = '\033[0;37m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[0;33m'
    RED = '\033[1;31m'
    REDINVERSE = '\033[1;37;41m'

    logging.addLevelName(logging.DEBUG, f'{WHITE}{logging.getLevelName(logging.DEBUG):.3}')
    logging.addLevelName(logging.INFO, f'{GREEN}{logging.getLevelName(logging.INFO):.3}')
    logging.addLevelName(logging.WARNING, f'{YELLOW}{logging.getLevelName(logging.WARNING):.3}')
    logging.addLevelName(logging.ERROR, f'{RED}{logging.getLevelName(logging.ERROR):.3}')
    logging.addLevelName(logging.CRITICAL, f'{REDINVERSE}{logging.getLevelName(logging.CRITICAL):.3}')
else:
    logging.addLevelName(logging.DEBUG, f'{logging.getLevelName(logging.DEBUG):.3}')
    logging.addLevelName(logging.INFO, f'{logging.getLevelName(logging.INFO):.3}')
    logging.addLevelName(logging.WARNING, f'{logging.getLevelName(logging.WARNING):.3}')
    logging.addLevelName(logging.ERROR, f'{logging.getLevelName(logging.ERROR):.3}')
    logging.addLevelName(logging.CRITICAL, f'{logging.getLevelName(logging.CRITICAL):.3}')


def deb(msg, newline=True):
    if not newline:
        handler.terminator = ''
    logger.debug(f'{_indent}{msg}')
    if not newline:
        handler.terminator = '\n'


def inf(msg, newline=True):
    if not newline:
        handler.terminator = ''
    logger.info(f'{_indent}{msg}')
    if not newline:
        handler.terminator = '\n'


def war(msg):
    logger.warning(f'{_indent}{msg}')


def err(msg):
    logger.error(f'{_indent}{msg}')


def die(msg, e=None, error_code=None):
    if logger.level == logging.DEBUG:
        print(traceback.format_exc())
    if error_code:
        exit_code = error_code.value
        logger.critical(f'now exiting due to critical error \'{ErrorCode.to_string(error_code.value)}\'')
    else:
        exit_code = 1
    if e:
        logger.critical(f'exception: {str(e)}')
    logger.critical(msg)
    os._exit(exit_code)


def human_file_size(filesize):
    sizes = [('bytes', 1, 0), ('KiB', 1024, 2), ('MiB', 1024 * 1024, 2), ('GiB', 1024 * 1024 * 1024, 2)]
    for label, divisor, digits in sizes:
        if filesize < divisor * 1024 or label == 'GiB':
            return f'{filesize/divisor:.{digits}f} {label}'
