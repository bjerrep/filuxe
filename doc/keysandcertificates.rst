
#######################################
Keys and certificates
#######################################


Self signed certificates for WAN SSL (HTTPS)::

    openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem.devel -keyout key.pem.devel -days 365

Accept everything except setting common name to the WAN hostname (or localhost for testing locally). The above line will give "Certificate for localhost has no `subjectAltName`" warnings from urllib3, which for now are simply silenced. Since the warning is for real the fix is to generate a certificate with a `subjectAltName` which is pending...

For a minimum amount of fuzz then manually make a directory called 'certificates' and run the openssl command from there. All templates and examples expects it to be this way.

The same certificate will have to be generated (or exist) on both the LAN server (to be used by the forwarder) and the WAN server (to be used by the WAN server itself).

