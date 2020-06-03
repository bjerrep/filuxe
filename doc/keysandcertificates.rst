
#######################################
Keys and certificates
#######################################


Self signed certificates for WAN SSL (HTTPS)

openssl req -x509 -newkey rsa:4096 -nodes -out cert.pem.devel -keyout key.pem.devel -days 365

Accept everything except setting common name to 'localhost'. The above line will give "Certificate for localhost has no `subjectAltName`" warnings from urllib3, which for now are simply silenced. Since the warning is for real the fix is to generate a certificate with a `subjectAltName` which is pending...

