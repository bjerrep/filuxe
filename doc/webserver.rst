
##############################
Web server
##############################

It is the same webserver application that is used for both LAN and WAN and each domain will provide an individual configuration file to its webserver instance. The webserver can run both HTTPS and plain HTTP, see
:doc:`here </keysandcertificates>` for generating a selfsigned certificate for HTTPS. For the sake of development and testing Filuxe the LAN is considered safe, and the LAN webserver runs with plain HTTP, while the WAN server is on the roaring internet and uses HTTPS.

Flask debugging is default off, to turn it on while developing launch the webserver as ::

    FLASK_DEBUG=1 ./filuxe_server.py ....



*************************
Write access
*************************

The WAN webserver requires a key for operations that modifies the filestorage. The idea beeing that the clients/products on the WAN that are otherwise able to access the webserver for downloading files wont be at risk for exposing write access to the webserver in case they get compromised. The forwarder service script operating from the LAN will be the only one who need to know the key for the WAN server and the LAN server runs without the key. The key can be found as "write_key" in the WAN server and the forwarder configuration files and should obviously be changed to something more exotic that the default key "devel".


*************************
Authentication
*************************

As a proof of concept the route '/' which is serving a static HTML page can be password protected if a username and a password is specified in the configuration file. Besides that this topic is just left as is for another day. There are (at least) two usecases that are in faviour of password protected access. The first is in case not a file but rather a URL to the WAN server is sent around the world. It will just appear to be not-very-professional if a file can be downloaded without the need for any credentials. The second usecase could be to protect against denial of service attacks where the server is flooded with a gazillion downloads.
See also `Flask basic HTTP AUTH <https://flask-httpauth.readthedocs.io/en/latest/>`_


*************************
Tips and tricks
*************************

When one or both of the LAN and WAN servers are just plainly refusing to talk nicely with e.g. the filuxe.py script then curl can be used to check if the servers are reachable and working as intended. The servers have a default route printing a single HTML text and this will be used to detect a working server. The curl commands below are assumed to be executed from the LAN.

**LAN, HTTP**::

    curl -v http://localhost:8000

The last part of the output is the HTML output from the server and it should read "filuxe_server_LAN".

**WAN, HTTPS**::

    curl --cacert certificates/cert.pem.devel -v https://<server>:9000 --insecure -u name:pwd

After a lot of SSL goblidigook the last HTML part should now contain "filuxe_server_WAN".






