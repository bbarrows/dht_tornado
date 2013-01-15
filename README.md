dht_tornado
===========

A BitTorrent "Mainline" DHT implementation using tornado

Here is the BEP. This is the BitTorrent Spec: http://www.bittorrent.org/beps/bep_0005.html

Here a few papers on the protocol:

Good general paper: ftp://ftp.tik.ee.ethz.ch/pub/students/2006-So/SA-2006-19.pdf

I preferred this one though because of the binary tree data structure: http://pdos.csail.mit.edu/~petar/papers/maymounkov-kademlia-lncs.pdf

Which I used in my implementation: https://github.com/bbarrows/dht_tornado

I was also able to talk a BitTorrent developer, Arvid, and ask a bunch of questions. 
The notes are in the https://github.com/bbarrows/dht_tornado repo under the DHTNotes file. 
Hopefully they make sense. I need to go back through and edit them as they were typed quickly
as he was talking.

I have created another project to bootstrap the DHT at https://github.com/bbarrows/dht_bootstrapper

And a project that brings it all together with a BitTorrent client at: https://github.com/bbarrows/dht_streamer
