from dht_bootstrapper import bht
import requests
from functools import partial
from bencode import bdecode, bencode
import hashlib, socket, array, time
from struct import *
import sys, re, random, thread, threading, os, re
from cStringIO import StringIO

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

class DHTPeer(object):
    def __init__(self, id, ip_port):
        self.id = id
        self.ip_port = ip_port

    def __hash__(self):
        return self.id

    def __cmp__(self, other):
        return str.__cmp__(self.id, other.id)

    def __eq__(self, other):
        return str.__eq__(self.id, other.id)

class DHTTreeLeaf(object):
    __slots__ = ['key', 'value', 'left', 'right']
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None

    def __sstr__(self):
        """Recursive __str__ method of an isomorphic node."""
        s = "  0\n"
        if self.left:
            s += "    l" + str(self.left)

        if self.right:
            s += "    r" + str(self.right)

        return s
        # Keep a list of lines
        lines = list()
        lines.append("0")#str(self.value))
        # Get left and right sub-trees
        l = str(self.left).split('\n')
        r = str(self.right).split('\n')
        #return '\n'.join(l) 

        #print l #alt = '| '
        #for line in l:
        #    lines.append(alt + line)

        #alt = '  '
        #for line in r:
        #    lines.append(alt + line)

        # Append first left, then right trees
        for branch in l, r:
            #lines.append("1")
            # Suppress Pipe on right branch
            alt = '| ' if branch is l else '  '
            lines.append(alt)
            for line in branch:
                # Special prefix for first line (child)
                prefix = alt #'+-' if line is branch[0] else alt
                lines.append(prefix + line)
        # Collapse lines
        return '\n'.join(lines)    

    def __repr__(self):
        ret_str = ""
        if self.value:
            ret_str += "V(%s)  " % self.value

        #if self.left:
        ret_str += "L(%s)  " % self.left

        #if self.right:
        ret_str += "R(%s)" % self.right
        
        return ret_str
        #return "V(%s)   L(%s) R(%s)" % (self.value, self.left, self.right)

    def __getitem__(self, key):
        """ x.__getitem__(key) <==> x[key], where key is 0 (left) or 1 (right) """
        return self.left if key == 0 else self.right

    def __setitem__(self, key, value):
        """ x.__setitem__(key, value) <==> x[key]=value, where key is 0 (left) or 1 (right) """
        if key == 0:
            self.left = value
        else:
            self.right = value

    def free(self):
        self.left = None
        self.right = None
        self.value = None
        self.key = None

class DHTTree(object):
    MAX_LIST_LENGTH = 2
    def __init__(self, peer_id):
        self._root = DHTTreeLeaf(None, None)
        self._add_branches_to_node(self._root)

        self.peer_id = peer_id
        self.bitmask = 1 << (20 * 8 - 1)    

    def _add_branches_to_node(self, node):
        node.left  = DHTTreeLeaf(0, [])
        node.right = DHTTreeLeaf(1, [])


    #Response for find_node, iterate down the tree
    #as far as possible to get a bucket to retunr
    def get_closest_node_bucket(self, key):
        pass

    def insert(self, dht_node): 
        key = dht_node.id
        bitmask = 1 << 7
        cur_char_index = 0
        cur_key_char = ord(key[cur_char_index])
        cur_peer_char = ord(self.peer_id[cur_char_index])

        cur_node = self._root
        same_branch = True

        while cur_node != None:
            next_bit = cur_key_char & bitmask

            if same_branch:
                same_branch = not( (cur_peer_char & bitmask) ^ next_bit)

            if next_bit:
                cur_node = cur_node.right
            else:
                cur_node = cur_node.left

            if cur_node and cur_node.value != None:
                if len(cur_node.value) >= DHTTree.MAX_LIST_LENGTH:
                    #import pdb; pdb.set_trace()
                    if same_branch:
                        nodes_to_re_add = cur_node.value
                        cur_node.value = None
                        self._add_branches_to_node(cur_node)
                        for n in nodes_to_re_add:
                            print "Readding %s" % n
                            self.insert(n)
                        self.insert(dht_node)
                        print "Done"
                        break
                    else:
                        for n in cur_node.value:
                            print "Checking %s" % n
                        print "Before:%s" % str(cur_node.value)
                        cur_node.value[DHTTree.MAX_LIST_LENGTH - 1] = key
                        print "After:%s" % str(cur_node.value)
                        break
                        pass #Check if last node is still valid, if not kcik off and add this one  
                else:
                    if dht_node not in cur_node.value:
                        cur_node.value.append(dht_node)  
                        break

                                 
            bitmask = bitmask >> 1
            if not bitmask:
                bitmask = 1 << 7
                cur_char_index = cur_char_index + 1
                cur_key_char = ord(key[cur_char_index])
                cur_peer_char = ord(self.peer_id[cur_char_index])
            #cur_node = next_node



class DHT(object):
    def __init__(self, port, bootstrap_ip_ports, node_id = None, io_loop = None):
        self.transaction_id = 0
        self.ip_ports = bootstrap_ip_ports

        if not node_id:
            self.id = gen_peer_id()
        else:
            self.id = node_id

        self.routing_table = DHTTree(self.id)

        self.port = port
        self.io_loop = io_loop or ioloop.IOLoop.instance()

        self.queries = {}
    
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.io_loop.add_handler(self.sock.fileno(), self.handle_input, self.io_loop.READ)

    def get_trasaction_id(self):
        self.transaction_id += 1

        if self.transaction_id >= 65534:
            self.transaction_id = 0
        
        return pack("H", self.transaction_id)

        #http://www.bittorrent.org/beps/bep_0005.html

        #PING
        #ping Query = {"t":"aa", "y":"q", "q":"ping", "a":{"id":"abcdefghij0123456789"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}

    def got_ping_response(self, original_query, response):
        #add responder.id to my RoutingTable
        transaction_id = response["t"]
        original_query = self.queries[transaction_id][0]
        ip_port = self.queries[transaction_id][1]
        print "<----%s--- PONG\n" % str(ip_port)

        self.routing_table.insert(DHTPeer(response['r']['id'], self.queries[transaction_id][1]))

        del self.queries[transaction_id]

        #find_node
        #find_node Query = {"t":"aa", "y":"q", "q":"find_node", "a": {"id":"abcdefghij0123456789", "target":"mnopqrstuvwxyz123456"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"0123456789abcdefghij", "nodes": "def456..."}}

    def find_node(self, node_id):
        pass


        #get_peers
        #get_peers Query = {"t":"aa", "y":"q", "q":"get_peers", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456"}}
        #Response with peers = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "values": ["axje.u", "idhtnm"]}}
        #Response with closest nodes = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "nodes": "def456..."}}
    def get_peers(self,info_hash):
        pass

        #announce_peer
        #announce_peers Query = {"t":"aa", "y":"q", "q":"announce_peer", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456", "port": 6881, "token": "aoeusnth"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}

    def announce_peer(self, info_hash, port, token):
        pass

    def ping(self, ip_port):
        print "PING ----%s--->\n" % str(ip_port)
        t_id = self.get_trasaction_id()
        ping_msg = {"t": t_id, "y": "q", "q": "ping", "a": {"id": self.id }}
        self.sock.sendto(bencode(ping_msg), ip_port)
        self.queries[t_id] = (ping_msg, ip_port)

    def handle_response(self, response):
        responder_id = response["r"]["id"]
        t_id = response["t"]

        print "In handle rsponse\n"
        if not self.queries.has_key(t_id):
            print "I dont have a transaction ID that matches this response"
            return

        original_query = self.queries[t_id][0]

        if original_query["q"] == "ping":
            self.got_ping_response(self.queries[t_id], response)
        elif original_query["q"] == "find_node":
            pass#self.got_find_node_response(responder, original_query, response)
        elif original_query["q"] == "get_peers":
            pass#self.got_get_peers_response(responder, original_query, response)
        elif original_query["q"] == "announce_peer":
            pass#self.got_announce_peer_response(responder, original_query, response)

    def handle_query(self, bdict):
        pass

    def handle_input(self, sock, fd, events):
        #import pdb; pdb.set_trace()
        #print "."
        data = self.sock.recv(4096)
        bdict = bdecode(data)

        #Got a response from some previous query
        if bdict["y"] == "r":
            self.handle_response(bdict)

        #Porb gonna have to ad a listenr socket
        #Got a query for something
        if bdict["y"] == "q":
            self.handle_query(bdict)

        #bdict['r']['id']
        #print "Got dict:%s" % bdict


    #XXX: This could block on sock.sendto, maybe do non blocking
    def start(self):
        for ip_port in self.ip_ports:
            self.ping(ip_port)

        self.io_loop.start() 
        #distance(A,B) = |A xor B| Smaller values are closer.

if __name__ == "__main__":
    dht = DHT(51414, ip_ports)
    dht.start()

    import pdb; pdb.set_trace();













