import json

config_file = None


def load_config(filename):
    global config_file
    config_file = filename
    with open(filename) as f:
        config = f.read()
        return json.loads(config)


def save_config(config, filename=config_file):
    with open(filename) as f:
        f.write(json.dumps(config))
