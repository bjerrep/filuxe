
###########################
Forwarder
###########################


The forwarder is running on the LAN server, it monitors the LAN filestorage for changes and updates the WAN webserver accordingly by e.g. uploading or deleting files over HTTP(S). It operates based on a rules file defining e.g. the maximum number of files in a given directory or which kind of files to forward from the LAN to the WAN server.


************************************************************
Rules
************************************************************

The rules file is in json and consist of a default section and a list of paths needing special settings. Both entries are optional and the rules file itself is optional as well. The default behavior of the forwarder is that all files are forwarded and that there are no limit for the number of files present on the wan server. Note that the forwarder will load the rules file 'rules.json' if it exist and no explicit rule file was given as argument with '--rules'.

**Basic rules:**

"export": true
    Makes it possible to exempt a directory from forwarding by setting "export" to false.

"include": ".*"
    Default is to include everything
    
"exclude": "(?!)"
    Default is to exclude nothing
    
"sync_at_startup": false
    Set to true to syncronize WAN fileserver during start. 
    
    
**Set a maximum on number of files:**
    
"max_files": -1
    Default is no limit to the number of files
    
"delete_by": "time"
    Requires a positive value for "max_files". 
    "time" is the default which will delete files from oldest first.
    "version" will delete files from lowest version first.
   
"version": "\.(\d+\.\d+\.\d+)\."
    Primary regex group for version matching. The regex shown above will look for the pattern ".number.number.number." in the filenames. It currently doesnt handle any 'rcX/ alpha/beta" style extensions which it probably should.
    


    
