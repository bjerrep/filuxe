
##############################
Web server direct HTTP
##############################


Rather than using filuxe.py to interact with the LAN webserver, you can use curl and wget for direct HTTP(S) access instead. Since the python script will follow the server script in case of breaking changes, filuxe.py will always be the safest bet for the job of adding and deleting files from the LAN webserver filestorage.

And the mandatory warning: never trust anything you download from the WAN webserver, HTTPS or not. It should be used with end to end encrypted files only. You would never ever work with plain zip files in real life as the examples on this page appears to be doing.


Upload file
-----------
Since the webservers on the LAN and WAN are exactly the same the upload can be used to with the WAN server just as well as the LAN server. That would obviously shortcircuit most of whatever filuxe does and render filuxe itself kind of moot. At time of this writing the commands **upload** and **delete** require a key for the server to accept them. This increases the security by approximately nothing, at least when running plain http.

::

    curl <host>/upload/<dest> -H "Content-Type:application/octet-stream" -H "key: secret_write_key" --data-binary @<src>



Get list of files
-----------------

::

    curl -s <LAN host>/filelist/

    {
      "filelist": {
        ".": {
          "here_is_a_file.zip": {
            "size": 12,
            "time": 1640218563.1022844
          },
          "here_is_another_file.zip": {
            "size": 56,
            "time": 1640218582.7589521
          }
        }
      },
      "info": {
        "dirs": 1,
        "fileroot": "test/filestorage_lan/",
        "files": 2
      }
    }

Alternatively "wget -A zip localhost:8000/files -O filelist"

Download file
-------------

This would be one way for products to download files from the WAN web server.

::

    wget <host>/download/test.zip
    ...
    2020-05-18 00:41:48 (560 KB/s) - 'test.zip' saved [11/11]

For self signed SSL certificates add '--no-check-certificate'. 
    
