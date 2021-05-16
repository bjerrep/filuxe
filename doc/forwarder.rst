
###########################
Forwarder
###########################

**Note:** *The forwarder has a file count limiter where it starts to delete files in a filestorage according to a "max_files" setting. Never enable this in the rules file described below if there are file storages with production files that may not be lost. There are countless ways this could happen, a forwarder gone south, the documentation on this page beeing wrong or outdated or perhaps just regex rules that did't quite work out as expected. Thread with care.*


The forwarder is intended to run on the LAN server where it monitors the LAN filestorage for changes and updates the WAN webserver accordingly by e.g. uploading or deleting files over HTTP(S). It operates based on a rules file defining which kind of files to forward from the LAN to the WAN server and as mentioned above, it can enforce a maximum number of files in a given directory.

Since the forwarder might be useful as just a file count limiter it can run on a LAN server even though there is no remote WAN server specified (meaning that it will never actually forward anything) and it can just as well run on a WAN server by telling it to use the WAN filestorage as the 'LAN filestorage'.

So if the forwarder should run on the WAN server for just using its file count limiter, its configuration could look like
::

    {
        "lan_filestorage": "test/filestorage_wan",
        "lan_host": "localhost",
        "lan_port": 9000
    }


************************************************************
Rules
************************************************************

The rules file is in json and consist of a default section and a list of directoris needing special settings. Both entries are optional and the rules file itself is optional as well. The default behavior of the forwarder is that all files are forwarded and that there are no limit for the number of files present on the wan server. Note that the forwarder will load the rules file 'rules.json' if it exist and no explicit rule file was given as argument with '--rules'.

A rules file could look like this:
::

    {
        "default": {
            "export": true,
            "sync_at_startup": true
            "max_files": 100
            "delete_by": "version"
        },
        "dirs": {
            "test": {
                "include": "zip",
                "max_files": 10,
                "group": ["(.*?)\\:\\d+\\.\\d+\\.\\d+\\:(.*)"]
            }
        }
    }


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

"max_files": -1
    Default is no limit to the number of files

"include": ".*"
    Default is to include everything

"exclude": "(?!)"
    Default is to exclude nothing

"delete_by": "time"
    Requires a positive value for "max_files".
    "time" is the default which will delete files from oldest first.
    "version" will delete files from lowest version first.

"version": "\\.(\\d+\\.\\d+\\.\\d+)\\."
    Primary regex group for version matching. The regex shown above will look for the pattern ".number.number.number." in the filenames. It currently doesnt handle any 'rcX/ alpha/beta" style extensions which it probably should.

"group": None
    If there are more than one type of files in a directory then a plain "max_files" putting all files in the same basket makes limited sense. It is possible to specify a list of "group" regex expressions which is used to divide similar files into specific groups. All files in a given group will then be held up against the "max_files" limit.

    Group expressions are tried in the order they are listed in the rules file and files that fails to be parsed by any regex expressions will end up in a common group (which is probably not what was wanted). A final group regex "(.*)" will make all otherwise unrecognized files end up in their own individual groups and then not be able to trigger any file deletions (which is probably not what was wanted either).

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
