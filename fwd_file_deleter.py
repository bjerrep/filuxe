from log import deb, inf, war
import fwd_util
import re, os


def get_rules_for_path(rules, path):
    """
    Return tuple with (max_files, delete_by, filegroups)
    """
    try:
        max_files = rules['dirs'][path]['max_files']
    except:
        try:
            max_files = rules['default']['max_files']
        except:
            deb('no file limit')
            return None, None, None
    if max_files <= 0:
        return None, None, None

    try:
        delete_by = rules['dirs'][path]['delete_by']
    except:
        try:
            delete_by = rules['default']['delete_by']
        except:
            delete_by = 'time'

    try:
        filegroups = rules['dirs'][path]['group']
    except:
        try:
            filegroups = rules['default']['group']
        except:
            filegroups = None

    return max_files, delete_by, filegroups


class Item:
    def __init__(self, x, directory, rules, delete_by):
        self.file = x[0]
        self.attr = x[1]
        self.numbers = None
        if delete_by == 'version':
            try:
                p = re.compile(rules['dirs'][directory]['version'])
                self.numbers = [int(x) for x in p.search(self.file).group(1).split('.')]
                if len(self.numbers) != 3:
                    self.numbers = None
                    war(f'failed to parse version from {self.file}')
            except:
                pass

        self.time = x[1]['time']

    def __lt__(self, other):
        if self.numbers and other.numbers:
            if self.numbers[0] < other.numbers[0]:
                return True
            if self.numbers[0] > other.numbers[0]:
                return False
            if self.numbers[1] < other.numbers[1]:
                return True
            if self.numbers[1] > other.numbers[1]:
                return False
            return self.numbers[2] < other.numbers[2]

        return self.time < other.time


class FileDeleter:
    def __init__(self, rules, dryrun=True):
        self.rules = rules
        self.dryrun = dryrun

    def delete_files(self, domain, filegroup):
        directory = filegroup['directory']
        filelist = filegroup['files']
        to_delete = len(filelist) - filegroup['maxfiles']

        if to_delete > 0:
            inf(f'deleting {to_delete} files from {domain.domain} filestorage, path={filegroup["directory"]}')
            _items = [Item(x, directory, self.rules, filegroup['deleteby']) for x in filelist.items()]
            _sorted_items = sorted(_items)

            for item in _sorted_items:
                fwd_util.print_file(item)
            for item in _sorted_items[:to_delete]:
                filepath = os.path.join(directory, item.file)
                if self.dryrun:
                    print(f'dryrun: not deleting {filepath}')
                else:
                    fwd_util.delete_file(filepath, domain)

    def parse_into_file_groups(self, domain, directory, file_groups, filelist, directory_settings):
        max_files, delete_by, file_group_rules = directory_settings
        deb(f'enforce file limit={max_files} in {domain.domain}, {filelist["info"]["files"]} files found')

        for filename, fileinfo in filelist['filelist'][directory].items():
            group_key = 'others'
            if file_group_rules:
                for group in file_group_rules:
                    match = re.match(group, filename)

                    if not match:
                        war(f'file {filename} not matching a group')
                        continue

                    nof_groups = len(match.groups())
                    nof_group_regex_groups = re.compile(group).groups

                    if nof_groups != nof_group_regex_groups:
                        deb(f'parsing {filename} failed, found {nof_groups} groups, not {nof_group_regex_groups}')
                    else:
                        group_key = ':'.join(match.groups())
                        break
            else:
                group_key = 'ungrouped'

            group_key = os.path.join(directory, group_key)
            try:
                file_groups[group_key]
            except:
                file_groups[group_key] = {}
                file_groups[group_key]['files'] = {}

            file_groups[group_key]['maxfiles'] = max_files
            file_groups[group_key]['deleteby'] = delete_by
            file_groups[group_key]['directory'] = directory
            file_groups[group_key]['files'][filename] = fileinfo

    def enforce_max_files(self, domain, path, recursive=False):
        try:
            filelist = fwd_util.get_filelist(domain, path, recursive)
            directories = filelist['filelist'].keys()

            groups_list = {}
            for directory in directories:
                directory_settings = get_rules_for_path(self.rules, directory)
                max_files, _delete_by, _file_groups = directory_settings
                if not max_files:
                    continue
                self.parse_into_file_groups(domain, directory, groups_list, filelist, directory_settings)

            for group_key, file_group in groups_list.items():
                nof_files = len(file_group['files'])
                if nof_files > file_group['maxfiles']:
                    deb(f'group {group_key} exceeded max files')
                    self.delete_files(domain, file_group)
        except Exception as e:
            deb(f'exception in enforce_max_files {str(e)}')
            return False
        return True
