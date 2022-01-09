import re, os
from log import deb, inf, war, err, die, Indent
from errorcodes import ErrorCode
import fwd_util


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
            deb(f'rules: "{path}" has no file limit')
            return None, None, []

    if max_files == 'unlimited':
        max_files = -1
    if max_files < 0:
        deb(f'rules: "{path}" has no file limit')
        return -1, None, []

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
            filegroups = []

    deb(f'rules: "{path}" has file limit {max_files}, delete by {delete_by}')
    return max_files, delete_by, filegroups


class Item:
    def __init__(self, x, directory, rules, delete_by):
        self.file = x[0]
        self.attr = x[1]
        self.numbers = None
        self.valid = False
        self.delete_by = delete_by

        if delete_by == 'version':
            try:
                p = re.compile(rules['dirs'][directory]['version'])
                self.numbers = [int(x) for x in p.search(self.file).group(1).split('.')]
                if len(self.numbers) == 3:
                    self.valid = True
                if not self.valid:
                    war(f'sort by version but failed to parse 3 digits from "{directory}/{self.file}"')

            except KeyError as e:
                war(f'sort by version but failed to parse 3 digits from "{directory}/{self.file}", key {e} not found')
            except AttributeError:
                war(f'version regex failed on filename "{os.path.join(directory, self.file)}"')
            except Exception as e:
                deb(f'exception {e}')

        else:
            self.time = x[1]['time']
            self.valid = True

    def __lt__(self, other):
        if not self.valid:
            raise Exception(f'invalid object used for less than operation "{self.file}"')

        if self.delete_by == 'version':
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
    def __init__(self, domain, dryrun=True):
        self.domain = domain
        self.dryrun = dryrun

    def delete_files(self, filegroup, group_name, use_http, rules):
        directory = filegroup['directory']
        filelist = filegroup['files']
        to_delete = len(filelist) - filegroup['maxfiles']
        deleted_files = []

        if to_delete > 0:
            delete_by = filegroup["deleteby"]

            inf(f'deleting {to_delete} files from {self.domain.domain} filestorage, '
                f'path="{filegroup["directory"]}" group "{group_name}". Deleteby={delete_by}')

            _items = [Item(x, directory, rules, delete_by) for x in filelist.items()]
            try:
                _sorted_items = sorted(_items)
            except:
                first_filename = list(filelist.keys())[0]
                war(f'failed running delete by "{delete_by}" in group "{group_name}". Files of type "{first_filename}"')
                return deleted_files

            deb(f'http filelist sorted by: "{delete_by}", delete from top')
            for index, item in enumerate(_sorted_items):
                if index < to_delete:
                    extra = 'DEL '
                else:
                    extra = 'KEEP'
                fwd_util.print_file(item, extra)

            for item in _sorted_items[:to_delete]:
                filepath = os.path.join(directory, item.file)
                if self.dryrun:
                    inf(f'dryrun: not deleting {filepath}')
                else:
                    try:
                        if use_http:
                            fwd_util.delete_http_file(self.domain, filepath)
                        else:
                            fqn = os.path.join(self.domain.root(), filepath)
                            inf(f'deleting {self.domain.log_path(fqn)}')
                            os.remove(fqn)
                            deleted_files.append(item.file)
                    except:
                        war(f'failed to delete file {fqn} (http={use_http})')

        return deleted_files

    def parse_into_file_groups(self, directory, filelist, directory_settings):
        file_groups = {}
        max_files, delete_by, file_group_rules = directory_settings
        deb(f'find groups in {self.domain.domain} "{directory}" ({len(filelist["filelist"][directory])} files)')

        for filename, fileinfo in filelist['filelist'][directory].items():
            group_key = 'ungrouped'

            for group in file_group_rules:
                try:
                    match = re.match(fr'{group}', filename)
                except Exception as e:
                    err(f'regex gave exception {e.__repr__()} with regex "{group}"')
                    exit(1)

                if not match:
                    deb(f'parsing {filename} failed, no regex match with {group}')
                else:
                    nof_groups = len(match.groups())
                    nof_group_regex_groups = re.compile(group).groups

                    if nof_groups != nof_group_regex_groups:
                        deb(f'parsing {filename} failed, found {nof_groups} groups, not {nof_group_regex_groups}')
                    else:
                        group_key = ':'.join(match.groups())
                        break

            if file_group_rules and group_key == 'ungrouped':
                inf(f'no group match for {filename}, adding to "ungrouped"')

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

        for group in file_groups.keys():
            deb(f'group {group} with {len(file_groups[group]["files"])} files')

        return file_groups

    def enforce_max_files(self, path, rules, recursive=True, use_http=False, lan_files=None):
        """
        Get the list of files (locally or over http) and delete files if required by
        the rule "max_files". It can run a full recursive scan-and-delete as is
        done when starting the forwarder (with an empty path and recursive=True),
        and it can run in a specific directory when triggered by a new or modified
        file (with a path and recursive=False).
        Returns nothing.
        """

        try:
            deb(f'enforce max files in {self.domain.domain} with path="{path}", dryrun={self.dryrun}')
            if use_http:
                filelist = fwd_util.get_http_filelist(self.domain, path, recursive, rules)
            else:
                if not lan_files:
                    scan_directory = self.domain.root()
                    filelist = fwd_util.get_local_filelist(scan_directory, path, recursive, rules)
                else:
                    filelist = lan_files

            try:
                directories = filelist['filelist'].keys()
            except:
                deb(f'got empty filelist from {self.domain.domain} at "{path}"')
                return

            group_list = {}
            for directory in directories:
                directory_settings = get_rules_for_path(rules, directory)
                max_files, _delete_by, _file_groups = directory_settings
                if max_files == -1:
                    inf(f'"{self.domain.domain}/{path}" has no filelimit, skipping.'
                        f' ({len(filelist["filelist"][directory])} files)')
                    continue
                if not max_files:
                    continue
                group_list[directory] = self.parse_into_file_groups(directory, filelist, directory_settings)

            deb(f'found total {len(group_list)} groups')

            for directory, group in group_list.items():
                for group_key, file_group in group.items():
                    nof_files = len(file_group['files'])
                    max_files = file_group['maxfiles']
                    excess_files = nof_files - max_files
                    if excess_files > 0:
                        message = f'"{self.domain.domain}/{directory}" group:"{group_key}" exceeded max files '\
                                  f'with {excess_files}. ({nof_files} files, limit is {max_files})'
                        inf(message)
                        with Indent() as _:
                            deleted_files = self.delete_files(file_group, group_key, use_http, rules)
                            for file in deleted_files:
                                del filelist['filelist'][directory][file]

                    else:
                        message = f'"{self.domain.domain}/{directory}" group:"{group_key}" no action. '\
                                  f'({nof_files} files, limit is {max_files})'
                        deb(message)

        except Exception as e:
            die(f'exception in enforce_max_files {e.__repr__()}', e, error_code=ErrorCode.INTERNAL_ERROR)
