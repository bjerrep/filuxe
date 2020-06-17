from log import deb, inf, war, cri
from util import chunked_reader
import os
from flask import Flask, request, abort, jsonify, send_from_directory, safe_join, render_template, Response, stream_with_context
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from flask_restful import inputs
from errorcodes import ErrorCode
from pathlib import Path
from functools import wraps

app = Flask(__name__)
auth = HTTPBasicAuth()

users = {}


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


@app.route('/download/<path:path>')
def get_file(path):
    filename = os.path.join(app.config['fileroot'], path)
    if not os.path.getsize(filename):
        return send_from_directory(app.config['fileroot'], path, as_attachment=True)
    else:
        return Response(stream_with_context(chunked_reader(filename)),
                        headers={'Content-Disposition': f'attachment; filename={path}',
                                 'Content-Type': 'application/octet-stream'})


@app.route('/upload/<path:path>', methods=['POST'])
@require_write_key
def route_upload(path):
    time = request.args.get('time', type=float, default=0.0)
    path = safe_join(os.path.join(app.config['fileroot'], path))
    if path is None:
        abort(404)

    dir = os.path.dirname(path)
    if not os.path.exists(dir):
        inf('constructing new path %s' % dir)
        Path(dir).mkdir(parents=True, exist_ok=True)

    try:
        # chunked upload
        range = request.environ['HTTP_CONTENT_RANGE']

        if os.path.exists(path) and range and range.startswith('bytes 0-'):
            # Currently the server refuses to rewrite an existing file. Should be a configuration option.
            war(f'file {path} already exist')
            return '', 403

        inf(f'writing file {path}')

        with open(path, "ab") as fp:
            fp.write(request.data)
    except:
        if os.path.exists(path):
            # Currently the server refuses to rewrite an existing file. Should be a configuration option.
            war(f'file {path} already exist')
            return '', 403

        inf(f'writing file {path}')

        with open(path, "wb") as fp:
            fp.write(request.data)

    if time > 0.0:
        deb(f'setting {path} time to {time}')
        os.utime(path, (time, time))

    # Created
    return '', 201


@app.route('/delete/<path:path>')
@require_write_key
def route_delete(path):
    path = safe_join(os.path.join(app.config['fileroot'], path))
    try:
        os.remove(path)
        inf('deleting %s' % path)
    except OSError:
        inf('failure while deleting %s' % path)
        return '', 404
    return '', 200


@app.route('/filelist/', defaults={'path': ''})
@app.route("/filelist/<path:path>")
def list_files(path):
    recursive = request.args.get('recursive', type=inputs.boolean, default=False)
    path = safe_join(os.path.join(app.config['fileroot'], path))
    files = {}
    directories = []
    inf('returning list from %s' % path)

    for _root, dirs, _files in os.walk(path):
        for dir in dirs:
            directories.append(dir)

        for file in _files:
            p = os.path.join(_root, file)
            relative = os.path.relpath(p, app.config['fileroot'])
            files[relative] = {'size': os.path.getsize(p), 'time': os.path.getatime(p)}

        if not recursive:
            break

    result = {'files': files, 'directories': directories}
    return jsonify(result)


@app.route('/api/<path:path>')
def get_server_status(path):
    if path == 'status':
        return jsonify({'status': 'ready'})


def start(args, cfg):
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
        ssl_context = (cfg['certificates'][0], cfg['certificates'][1])
    except:
        ssl_context = False

    inf(f'{realm} server running at http{"s" if ssl_context else ""}://{host}:{port}. Filestorage root {file_root}')

    if not os.path.exists(file_root):
        try:
            os.makedirs(file_root)
        except:
            cri('unable to create file root %s, please make it yourself and fix permissions' %
                file_root,
                ErrorCode.SERVER_ERROR)

    app.config['fileroot'] = file_root
    app.secret_key = os.urandom(50)
    app.name = f'filuxe_server_{realm}'
    try:
        app.config['writekey'] = cfg['wan_write_key']
    except:
        app.config['writekey'] = ''

    try:
        users = {cfg['username']: generate_password_hash(cfg['password'])}
        inf('HTTP-AUTH enabled')
    except:
        inf('HTTP-AUTH disabled')

    if ssl_context:
        app.run(host=host, port=port, ssl_context=ssl_context)
    else:
        app.run(host=host, port=port)
    return ErrorCode.OK
