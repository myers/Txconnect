# Txconnect - DirectConnect client with Web UI


> Direct Connect (DC) is a peer-to-peer file sharing protocol. Direct Connect clients connect to a central hub and can download files directly from one another. 
> -- [Wikipedia](http://en.wikipedia.org/wiki/Directconnect)

Txconnect runs as a daemon on your server computer.  Unlike other DC++ software that I could find on Linux it can handle sharing 4TiB without freaking out.  It supports these features:

 * NMDC protocol ([ADC](http://en.wikipedia.org/wiki/Advanced_Direct_Connect) not yet supported)
 * Web UI that allows you to chat and download files from your browser
 * JSON REST API to control from scripts  
 * Plugin system

![Screenshot of Search Results in the WebUI](docs/screenshots/search_results.jpg)

## Quick Start

Tested on Ubuntu 12.04 and Mac OS X.

Download this code and install in a [virtualenv](http://www.virtualenv.org/en/latest/).  Install all the needed 3rd party libraries via pip.

    git clone <git url>
    cd Txconnect
    pip install virtualenv
    virtualenv venv
    . venv/bin/activate
    pip install -r requirements.txt

To run the app
    
    PYTHONPATH=. venv/bin/twistd --nodaemon txconnect
    
Once you run it once, there will be a config file in `~/.txconnect/config.yml` where you can set what hubs you want to connect to.

## JSON REST API

The easiest way to use the API is in a python script.  You can import the
`txconnect.api_client`.  Here's an example script that will do a search for
"foobar" and show the results.

     import pprint
     from txconnect.api_client import ApiClient
     client = ApiClient('http://localhost:9000/api')
     pprint.pprint(client.search("Foobar"))

## DirectConnect Protocol Docs

http://nmdc.sourceforge.net/NMDC.html

## other projects 

http://github.com/blakef/pydirectconnect
http://github.com/rlane/dci
