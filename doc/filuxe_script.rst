
##############################
Filuxe script
##############################


The filuxe.py script can be used for accessing the LAN and WAN filestorages over HTTP(S). It follows the filuxe philosophy of going all in on HTTP filetransfers via python scripts. Do however keep in mind that what it does is to work on a filestructure on a local server which probably sounds familiar, and that it does so without any builtin security. So if corporate access control is required then SMB or NFS mounts does pretty much the same, but with proper access control.

filuxe.py can be used to upload, download and delete files on either filestorage and it can be used to get a list of files on either as well. filuxe.py is only envisioned to be used on the LAN, the expectation is that accesses to the WAN filestorage by e.g. products will be done with a plain wget rather than with the filuxe python script. That might however be a flawed expectation.

It will as any other filuxe script need a configuration file. It will have a preference for accessing the LAN filestorage so if it can find a "lan_host" and a "lan_port" entry then this is what it will be using. If LAN entries are not present it will load the wan server address instead. Typically it can therefore be launched with the LAN server config directly or a copy of the forwarder config where the LAN references are deleted forcing it to fall back to WAN access.


The filuxe.py script is just a thin facade on top of the filuxe core script which filuxe.py uses together with the forwarder script for working with HTTP filetransfers.

