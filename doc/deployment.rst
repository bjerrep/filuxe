
##############################
Deployment
##############################


Since the state of the filuxe project is currently play-along-for-fun talking about deployment might be a little pretentious. But still it makes sense to have a page focusing on what needs to be done when filuxe is installed outside a developer pc.


LAN Webserver
==============
The default LAN webserver is completely open. If that doesn't sound right then make one or more of the following changes in the configuration file:

- make "username" and "password" entries (still just for basic auth).
- make the server run HTTPS by supplying it with a "lan_certificate" entry.
- add a "write_key" needed for operations modifying the LAN filestorage

If about to add everything in then consider to base the LAN configuration file on the WAN configuration file since it uses all of the above.

Change "lan_host" from "localhost" to "0.0.0.0" to make the server listen to all adresses.


WAN Webserver
==============
Change the "username", "password" and "write_key" entries to something different from the defaults.

Certificates
==============
If self signing SSL certificates for HTTPS then remember to re-run openssl whenever the host is changed.


Others
==============
Change any systemd service scripts to be owned and writable by root only.

The rest of filuxe is running as a plain user, including the configuration files, which is rather unambitious. This is just how it is currently.



