from dht_bootstrapper import bht
import requests
from functools import partial
from bencode import bdecode, bencode
import hashlib, socket, array, time
from struct import *
import sys, re, random, thread, threading, os, re
from cStringIO import StringIO

from bintrees import BinaryTree

from tornado import ioloop
from tornado import iostream

#This just returns a random number between 0 and MAX 32 Bit Int
def gen_unsigned_32bit_id():
    return random.randint(0, 0xFFFFFFFF)
    
#This just returns a random unsigned int
def gen_signed_32bit_id():
    return random.randint(-2147483648, 2147483647)    
    
#Generates a string of 20 random bytes
def gen_peer_id():
    return gen_random_string_of_bytes(20)

def gen_random_string_of_bytes(length):
    return ''.join(chr(random.randint(0,255)) for x in range(length))

ip_ports = [('180.35.205.227', 31559), ('99.248.254.29', 41959), ('94.225.104.219', 53154), ('188.168.217.194', 30455), ('71.225.73.243', 15804), ('46.98.7.219', 50586), ('79.116.40.153', 30832), ('109.193.5.98', 34776), ('178.48.61.57', 45204), ('93.120.198.189', 19794), ('2.9.25.254', 42445), ('93.84.102.26', 48523), ('84.29.0.136', 49858), ('91.122.102.181', 56763), ('175.180.182.202', 11625), ('46.129.17.241', 37756)]

class DHTNode(object):
    def __init__(self, ip_port, id):
        self.id = id
        self.queries = {}
        self.ip_port = ip_port


class DHT(object):
    def __init__(self, port, bootstrap_ip_ports, node_id = None, io_loop = None):
        self.ip_ports = bootstrap_ip_ports

        self.routing_table = BinaryTree()
        self.routing_table.insert(None,None)

        if not node_id:
            self.id = gen_peer_id()
        else:
            self.id = node_id

        self.port = port
        self.io_loop = io_loop or ioloop.IOLoop.instance()

        self.querying_nodes = {}

        #http://www.bittorrent.org/beps/bep_0005.html

        #PING
        #ping Query = {"t":"aa", "y":"q", "q":"ping", "a":{"id":"abcdefghij0123456789"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}

    def got_ping_response(responder, original_query, bdict):
        #add responder.id to my RoutingTable
        print "Got a response from %s" % responder.id
        pass

        #find_node
        #find_node Query = {"t":"aa", "y":"q", "q":"find_node", "a": {"id":"abcdefghij0123456789", "target":"mnopqrstuvwxyz123456"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"0123456789abcdefghij", "nodes": "def456..."}}

        #get_peers
        #get_peers Query = {"t":"aa", "y":"q", "q":"get_peers", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456"}}
        #Response with peers = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "values": ["axje.u", "idhtnm"]}}
        #Response with closest nodes = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "nodes": "def456..."}}

        #announce_peer
        #announce_peers Query = {"t":"aa", "y":"q", "q":"announce_peer", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456", "port": 6881, "token": "aoeusnth"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}

    def handle_response(self, bdict):
        responder_id = bdict["r"]["id"]
        if self.querying_nodes.has_key(responder_id):
            responder = self.querying_nodes[responder_id]
            trans_id = bdict["t"]
            if responder.queries.has_key(trans_id):
                original_query = responder.queries[trans_id]
                if original_query["q"] == "ping":
                    self.got_ping_response(responder, original_query, bdict)
                elif original_query["q"] == "find_node":
                    pass#self.got_find_node_response(responder, original_query, bdict)
                elif original_query["q"] == "get_peers":
                    pass#self.got_get_peers_response(responder, original_query, bdict)
                elif original_query["q"] == "announce_peer":
                    pass#self.got_announce_peer_response(responder, original_query, bdict)
            else:
                print "I havent asked them about this before"
        else:
            print "It doesnt seem like I have asked this node anything before"

        pass

    def handle_query(self, bdict):
        pass

    def handle_input(self, sock, ip_port, fd, events):
        #import pdb; pdb.set_trace()
        print "."
        data = sock.recv(4096)
        bdict = bdecode(data)

        #Got a response from some previous query
        if bdict["y"] == "r":
            self.handle_response(bdict)

        #Porb gonna have to ad a listenr socket
        #Got a query for something
        if bdict["y"] == "q":
            self.handle_query(bdict)

        #bdict['r']['id']
        print "Got dict:%s" % bdict



    #XXX: This could block on sock.sendto, maybe do non blocking
    def start(self):
        ping_msg = bencode({"t":"a1", "y":"q", "q":"ping", "a":{"id": self.id }})

        for ip_port in self.ip_ports:
            print "----%s--->\n" % str(ip_port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.io_loop.add_handler(sock.fileno(), partial(self.handle_input, sock, ip_port), self.io_loop.READ)
            sock.sendto(ping_msg, ip_port)

        self.io_loop.start() 
        #distance(A,B) = |A xor B| Smaller values are closer.

if __name__ == "__main__":
    dht = DHT(51414, ip_ports)
    dht.start()
    #info_hash = "2110c7b4fa045f62d33dd0e01dd6f5bc15902179"
    #get_peers_msg = bencode({"t":"aa", "y":"q", "q":"get_peers", "a": {"id":peer_id, "info_hash":info_hash.decode("hex")}})
        #{'t':0, 'y':'q', 'q':'get_peers', 'a': {'id':peer_id, 'info_hash':info_hash.decode("hex")}})
    


    import pdb; pdb.set_trace();













