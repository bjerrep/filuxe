import os, re
from pathlib import Path
from functools import wraps
from flask import Flask, request, abort, jsonify, send_from_directory,\
    render_template, Response, stream_with_context
from flask_httpauth import HTTPBasicAuth
from flask_restful import inputs
from werkzeug.security import generate_password_hash, check_password_hash
from log import deb, inf, war, err, die, human_file_size
from util import chunked_reader, file_is_closed, get_file_time
from errorcodes import ErrorCode

import urllib3
urllib3.disable_warnings()

try:
    from werkzeug.utils import safe_join
except:
    # older installations
    from flask import safe_join

app = Flask(__name__)
auth = HTTPBasicAuth()

users = {}
chunked_file_handle = {}

with open('version.txt') as f:
    filuxe_server_version = f.read().strip()


def require_write_key(fn):
    @wraps(fn)
    def verify_key(*args, **kwargs):
        if not app.config['writekey'] or request.headers.get('key') == app.config['writekey']:
            return fn(*args, **kwargs)
        else:
            inf('unauthorized write')
            abort(403)
    return verify_key


@auth.verify_password
def verify_password(username, password):
    return not users or (username in users and check_password_hash(users.get(username), password))


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(directory='templates', filename='logo.png')


@app.route('/')
@auth.login_required
def index():
    return render_template('index.html', name=app.name)


@app.route('/stats')
def route_stats():
    stats = {
        'version': filuxe_server_version
    }
    return jsonify(stats), 200


@app.route('/download/<path:path>')
def get_file(path):
    filename = os.path.join(app.config['fileroot'], path)
    try:
        if not os.path.getsize(filename):
            return send_from_directory(app.config['fileroot'], path, as_attachment=True)
        else:
            return Response(stream_with_context(chunked_reader(filename)),
                            headers={'Content-Disposition': f'attachment; filename={path}',
                                     'Content-Type': 'application/octet-stream'})
    except FileNotFoundError:
        err(f'download request failed, file not found "{path}"')
        abort(404)


@app.route('/upload/<path:path>', methods=['POST'])
@require_write_key
def route_upload(path):
    global chunked_file_handle
    time = request.args.get('time', type=float, default=0.0)
    force = request.args.get('force', type=inputs.boolean, default=False)
    path = safe_join(os.path.join(app.config['fileroot'], path))
    if path is None:
        abort(404)

    try:
        content_range = request.environ['HTTP_CONTENT_RANGE']
        parsed_ranges = re.search(r'bytes (\d*)-(\d*)\/(\d*)', content_range)
        _from, _to, _size = [int(x) for x in parsed_ranges.groups()]
        deb(f'chunked upload, {_from} to {_to} ({_size}), {_to - _from + 1} bytes')
    except:
        content_range = None

    if not content_range or _from == 0:
        if os.path.exists(path):
            if not force:
                # if force was not given then the default is that the server refuses to rewrite an existing file
                err(f'file {path} already exist, returning 403 (see --force)')
                return '', 403
        else:
            directory = os.path.dirname(path)
            if not os.path.exists(directory):
                inf(f'constructing new path {directory}')
                Path(directory).mkdir(parents=True, exist_ok=True)

    if content_range:
        if _from == 0:
            try:
                if chunked_file_handle.get(path):
                    err('internal error in upload, non closed filehandle')
                    chunked_file_handle[path].close()
                open(path, 'w').close()
                chunked_file_handle[path] = open(path, "ab")
            except:
                pass

            inf(f'writing file "{path}" ({human_file_size(_size)})')

        chunked_file_handle[path].write(request.data)

        if _to == _size - 1:
            inf(f'{path} transfer complete')
            chunked_file_handle[path].close()
            del chunked_file_handle[path]

    else:
        # ordinary non-chunked upload, single write
        inf(f'writing file "{path}"')
        with open(path, "wb") as fp:
            fp.write(request.data)

    if time > 0.0:
        deb(f'setting {path} time to {time}')
        os.utime(path, (time, time))

    # 201: Created
    return '', 201


@app.route('/delete/<path:path>')
@require_write_key
def route_delete(path):
    path = safe_join(os.path.join(app.config['fileroot'], path))
    try:
        os.remove(path)
        inf(f'deleting file "{path}"')
    except OSError:
        inf(f'file not found deleting "{path}"')
        return '', 404
    return '', 200


@app.route('/filelist/', defaults={'path': ''})
@app.route("/filelist/<path:path>")
def list_files(path):
    recursive = request.args.get('recursive', type=inputs.boolean, default=False)
    path = safe_join(os.path.join(app.config['fileroot'], path))
    if not os.path.exists(path):
        err(f'filelist failed, path not found "{path}"')
        return 'path not found', 404
    fileroot = os.path.join(app.config['fileroot'], '')
    file_result = {}
    dir_result = []
    nof_files = 0

    for _root, dirs, _files in os.walk(path):
        for file in _files:
            p = os.path.join(_root, file)
            if not file_is_closed(p):
                war(f'skipping {p} since it is busy')
                continue
            relative = os.path.relpath(_root, fileroot)
            if not file_result.get(relative):
                file_result[relative] = {}
            file_result[relative][file] = {'size': os.path.getsize(p), 'time': get_file_time(p)}

        for directory in dirs:
            rel_path = os.path.join(os.path.relpath(_root, fileroot), directory)
            dir_result.append(os.path.normpath(rel_path))

        nof_files += len(_files)

        if not recursive:
            break

    extra = "(recursive)" if recursive else ""

    inf(f'returning filelist at "{path}", {nof_files} files and {len(dir_result)} directories. {extra}')

    ret = {'info':
               {
                   'fileroot': fileroot, 'files': nof_files, 'dirs': len(dir_result)
               },
           'filelist': file_result,
           'dirlist': dir_result}
    return jsonify(ret)


@app.route('/api/<path:path>')
def get_server_status(path):
    if path == 'status':
        return jsonify({'status': 'ready'})


def start(_, cfg):
    global users
    try:
        file_root = cfg['wan_filestorage']
        host = cfg['wan_host']
        port = cfg['wan_port']
        realm = 'WAN'
    except:
        file_root = cfg['lan_filestorage']
        host = cfg['lan_host']
        port = cfg['lan_port']
        realm = 'LAN'

    try:
        for i in (0, 1):
            if not os.path.exists(cfg['certificates'][i]):
                die(f'specified certificate not found, "{cfg["certificates"][i]}"')
        ssl_context = (cfg['certificates'][0], cfg['certificates'][1])
    except:
        ssl_context = False

    if not os.path.exists(file_root):
        try:
            os.makedirs(file_root)
        except:
            die(f'unable to create file root {file_root}, please make it yourself and fix permissions',
                ErrorCode.SERVER_ERROR)

    app.config['fileroot'] = file_root
    app.secret_key = os.urandom(50)
    app.name = f'filuxe_server_{realm}'
    try:
        app.config['writekey'] = cfg['write_key']
    except:
        app.config['writekey'] = ''

    try:
        users = {cfg['username']: generate_password_hash(cfg['password'])}
        inf('HTTP-AUTH enabled')
    except:
        inf('HTTP-AUTH disabled')

    inf(f'filuxe {realm} server {filuxe_server_version} running at http{"s" if ssl_context else ""}://{host}:{port}')
    inf(f'filestorage root "{file_root}"')

    if ssl_context:
        app.run(host=host, port=port, ssl_context=ssl_context)
    else:
        app.run(host=host, port=port)
    return ErrorCode.OK
