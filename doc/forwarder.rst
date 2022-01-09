
###########################
Forwarder
###########################

**Note:** *The forwarder has a file count limiter where it starts to delete files in a filestorage according to a "max_files" setting. Never enable this in the rules file described below if there are file storages with production files that may not be lost. There are countless ways this could happen, a forwarder gone south, the documentation on this page beeing wrong or outdated or perhaps just regex rules that did't quite work out as expected. Thread with care.*


The forwarder is intended to run on the LAN server where it monitors the LAN filestorage for changes and updates the WAN webserver accordingly by e.g. uploading or deleting files over HTTP(S). It operates based on a rules file defining which kind of files to forward from the LAN to the WAN server and as mentioned above, it can enforce a maximum number of files in a given directory. The use case is a build system which can now upload artifacts from high speed development branches/assets without worrying (too much) about disks running full with obsolete artifacts.

Since the forwarder might be useful as just a file count limiter it can run on a LAN server even though there is no remote WAN server specified (meaning that it will never actually forward anything) and it can just as well run on a WAN server by telling it to use the WAN filestorage as the 'LAN filestorage'.

The forwarder arguments:
::
    ./filuxe_forwarder.py -h
    usage: filuxe_forwarder [-h] [--config CONFIG] [--rules RULES] [--templaterule] [--dryrun] [--verbose] [--info]

    optional arguments:
    -h, --help       show this help message and exit
    --config CONFIG  configuration file, default config_forwarder.json
    --rules RULES    rules json file. Default is an empty rule set forwarding everything
    --templaterule   make an example rules.json file
    --dryrun         don't actually delete files
    --verbose        enable verbose messages
    --info           enable informational messages

************************************************************
Config
************************************************************

The forwarder requires a configuration file telling it where to find the servers. It can be regarded as containing the parts from the LAN and WAN server configuration files that the forwarder should use. 

If the forwarder should run on a server for just using its file count limiter, its configuration could look like
::

    {
        "lan_filestorage": "test/filestorage_lan",
        "lan_host": "localhost",
        "lan_port": 8000
    }

Since there is no wan settings present the actual forwarding is disabled and this forwarder will only be useful as file count limiter given it has a matching rules configuration (next chapter). Since this is most likely the same configuration as the LAN server is using the forwarder can simply be given the LAN server configuration.


The typical forwarder configuration with forwarding from a LAN to a WAN will look something like:
::
    {
        "lan_filestorage": "test/filestorage_lan",
        "lan_host": "localhost",
        "lan_port": 8000,
        "wan_host": "localhost",
        "wan_port": 9000,
        "wan_certificate": "test/certificates/cert.pem.devel",
        "certificates": [
            "test/certificates/cert.pem.devel",
            "test/certificates/key.pem.devel"
        ],
        "write_key": "devel"
    }

Since there are a certificate entry for the WAN server this will be contacted via https where the LAN server by the same logic will use plain http. This configuration is then the merge of the configuration files used for both the LAN and the WAN servers.

There are some forwarder configuration example files used by the live test in config/fwd.




************************************************************
Rules
************************************************************

The rules file is needed only if forwarding should be changed from the default 'just forward everything as is' and/or the file deleter should be activated with 'max_files' different from the default implicit value of 'unlimited'.

The rules file is in json and consist of a default section and a list of directories needing special settings. Both entries are optional and the rules file itself is optional as well. The default behavior of the forwarder is that all files are forwarded and that there are no limit for the number of files.

A rules file could look like this:
::

    {
        "default": {
            "include": [".*\\.zip"],
            "max_files": 2
        },
        "dirs": {
            "first": {
                "max_files": 1,
                "exclude": ["unversioned_..zip"],
                "version": ".*?:(\\d+.\\d+.\\d+):.*?",
                "group": ["(.*?)\\:\\d+\\.\\d+\\.\\d+\\:(.*)"],
                "delete_by": "version"
            },
            "second": {
                "include": [".*"],
                "max_files": "unlimited"
            },
            "second/second": {
                "max_files": 2
            }
        }
    }

Take care. In the rule set above e.g. the 'max_files' equal 2 in the default section will be the default for all directories found recursively which might lead to a lot of unintended file deletions. Use the --dryrun argument on the forwarder in order to spot any unexpected behaviour, with --dryrun no files will actually be deleted.

Forwarder rules files used by the live test can be found in config/rules and the example above is live_test_forwarder_as_deleter.json. A matching testset with files and that exercises these rules can be found in testdata/filestorage_lan.

Note that the default section is the same as the rule for the root directory meaning that settings here will be default inherited for all directories in the entire directory tree. Rules for a given directory is the rules inherited from the parent directory with any explicit rules in a given directory -rewriting- the rules inherited from the parent.

**Default rules:**

"export": true
    Setting "export" to false makes it possible to exempt a directory from forwarding from LAN to WAN.

"delete": false
    Setting "delete" to true will make the forwarder delete files deleted on the LAN filestorage on the WAN filestorage as well. If "export" is true and "delete" is true then the WAN filestorage will be a replica of the LAN filestorage.

"sync_at_startup": false
    Set to true to syncronize WAN fileserver during start.

**Directory rules**

These settings can be listed in the default section as well but if they are present in a
given directory section these will take precedence.

"max_files": "unlimited"
    Default is no limit to the number of files. Otherwise the limit as a plain integer.

"include": ".*"
    Default is to include everything

"exclude": "(?!)"
    Default is to exclude nothing

"delete_by": "time"
    Requires a positive value for "max_files". |br|
    "time" is the default which will delete files from oldest first. |br|
    "version" will delete files from lowest version first and requires a "version" regex, see below. |br|
    The third criteria would be "age" but this is not implemented yet.

"version": "\\.(\\d+\\.\\d+\\.\\d+)\\."
    Primary regex group for version matching. The regex shown above will look for the pattern ".number.number.number." in the filenames. It currently doesnt handle any 'rcX/ alpha/beta" style extensions which it probably should.

"group": None
    If there are more than one type of files in a directory then a plain "max_files" putting all files in the same basket makes limited sense. It is possible to specify a list of "group" regex expressions which is used to divide similar files into specific groups. All files in a given group will then be held up against the "max_files" limit.

    Group expressions are tried in the order they are listed in the rules file and files that fails to be parsed by any regex expressions will end up in a common group called "ungrouped" (which is probably not what was wanted). A final group regex "(.*)" will make all otherwise unrecognized files end up in their own individual groups with a matching filecount of 1 and they will then not be able to trigger any file deletions (which is probably not what was wanted either).

An example with the "group" `["(.*?)\\:\\d+\\.\\d+\\.\\d+\\:(.*)"]` containing a single regex:

::

    Files                                       Internal group key
    a:1.1.1:anytrack:anyarch:unknown.zip        a:anytrack:anyarch:unknown:zip
    a:1.1.2:anytrack:anyarch:unknown.zip        a:anytrack:anyarch:unknown:zip
    a:1.1.3:anytrack:anyarch:unknown.zip        a:anytrack:anyarch:unknown:zip
    b:1.1.3:anytrack:anyarch:unknown.zip        b:anytrack:anyarch:unknown:zip

So if "max_files" is 1 and files are deleted by version "\\:(\\d+\\.\\d+\\.\\d+)\\:" then the remaining files will be (*)

::

    a:1.1.3:anytrack:anyarch:unknown.zip
    b:1.1.3:anytrack:anyarch:unknown.zip

(*) at least in theory.



.. |br| raw:: html

      <br>
