# ideas

Use json-rpc 2.0 http://jsonrpc.org/specification for the webui system. 
Events could just be a rpc call with the browser as the "server"

# urgent

## ForceMove

## make directory downloads transfer their priority to the downloads they cause

## create a thread in dbthread only for $Search requests, make use of it in sharestore.py

## why are downloads that are complete still in the queue?
  /comics/dc/finished/Ismelda/Fansadox Collection 251 - Fernando - Dead Shark Island 2 - Forsaken.cbz
   * added logging to see why
## why are there downloads for users that are online, but we are not trying to download from them
  * http://gir.maski.org:9000/queuestore/ lists a bunch of users online that have files we want
    * maybe first step would paint them green if we are waiting to or are connected to them
    * button to make a download start

## page that shows me the peers we are actually connected to
   * clean up webui that shows being connected to peers that we are not

## when looking for a file to search for sources, don't get non multisource capable files

## put txconnect on github

## wiki docs on writing plugins

## make private msgs that start with ! fire an event, look for a cancel in the event return vals, then fire the event the ui would look for

## why does sending ! always disconnect

# txconnect
## Web UI

* use the progress bar found at the bottom of http://www.the-art-of-web.com/css/timing-function/ to show how long 
you need to wait for a search to start

## more hubs

* pre priority limits
 * config 

 limits:
   daily:
     - 0: 5368709120
     - 1: 1024 # so if we've downloaded 5368709120
    
 * LimitedQueueStore - which wraps QueueStore
 * requery every 5 minutes

 * or have TrafficLogger do a query and emit an event when it thinks we are over

* per hub share list
 * webui to test this

* show progress for filelist downloads

* need to survive being disconnected.

* hub reconnect time needs to be lower

* use process protocols to put the hasher in one or more other process http://twistedmatrix.com/documents/current/core/howto/process.html

## next step

special event flag for hub:user:new when we are just connecting vs.  if this flag is set then wait 5 seconds before acting on it.

rerun this when a download is finished

column in queuestore for the last time we saw a peer that had this file

## itches

* hub tab in webui, go to start page come back, scrolled to the top of the chat pane
* datetimes on hub status messages

* test new indexing code
* decorator for db methods that automaticly run them on the right thread
* hub login - can't be hacks for each hub server software
* rename type to filetype in search / download code
* multisource downloading
* filelist downloader
* put peer downloads in real table that can be sorted (js ui stuff)
* show a row in peer monitor when we are retrying a peer or connecting to a peer
* '$ADCGET list /DC\\ Downloads/0-day/2010-08-12/0-day/ 0 -1'

## must have 

* private message support
* no traces of hacks - shallow git clone
* automatic indexing
* read over every line in code
* download progress (what we have now is transfer progress)

## nice to have

* download queue auto update
* fix download queue left side pane when you have a lot of downloads

## won't have

* incremental files.xml.bz2 updates
* public hub discovery
* adc support

 * what do other dc clients do when asked for a tthl of a has they don't have?

## before connecting to the usual suspects

 * http://codespeak.net/lxml/tutorial.html
 * tth sum in another process (1 per cpu) http://code.google.com/p/twisted-parallels/source/browse/trunk/ex1producer.py

 * bugfix: handle wanting to d/l from peer while they want to d/l from us
 * bugfix: handle dir download. make sure we return the right thing when iteraing thru files/dirs under a dir

 * allow to delete from download queue (single, multi)

 * allow indexing to be started and monitored from the web ui

 * better CSS for chat messages
  * use fixed font, css table, timestamp (x mins ago)
 * http://chris-barr.com/entry/disable_text_selection_with_jquery/
 * fix scrolling

 * view filelist
 * email errors to myself

 * plugin system 
  * filelist getter as a plugin
  * transfer log
 * multisource downloads with tth verification

## DC client

* Next Action: every 5 minutes rescan the current peers for downloads

* catch TimeoutErrors and add those to the retry queue.

* add more to the dc file source that exposes the complete/incomplete
folders with work names (if we have them)

* write unit test that uses ZipFile/RarFile in another thread to
download the intresting bits from DC and make an Collection and
CollectionArchive entry for zip/rar files.
  - put this into production

* fix log.debug usage so the warning stop showing

* write more unit tests in general

* file.xml.bz2 file don't show the right % when downloading
 
* fix load_dcindex so that it doesn't delete files that we've gotten the
bitzi of 

* Allow the bot to annouce new things to those who subscribe or don't
unsubscribe

* clean up code for release 
 * create python setup and package
 * wiki page on starting it up
 * Announce on twisted list and p2p list
 * pypi

