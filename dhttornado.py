from dht_bootstrapper import bht
import requests
from functools import partial
from bencode import bdecode, bencode
import hashlib, socket, array, time
from struct import *
import sys, re, random, thread, threading, os, re
from cStringIO import StringIO
from heapq import heappush, heappop, nsmallest

from tornado import ioloop
from tornado import iostream

#This is just an array from the bootrstrap (bht) project I have
#That I am using for testing right now
ip_ports = [('24.78.64.8', 31039), ('67.70.36.33', 60982), ('31.39.223.125', 52935), ('67.166.139.156', 36573), ('96.249.147.62', 15981), ('63.228.86.94', 19952), ('189.231.247.83', 43771), ('189.161.90.111', 43015), ('89.134.121.10', 28406), ('186.212.242.90', 49385), ('190.192.169.76', 10205), ('79.179.14.213', 46010), ('46.119.19.254', 25811), ('99.241.15.176', 31135), ('98.204.250.236', 22564), ('74.109.214.106', 55066), ('78.63.253.15', 64021), ('46.241.0.98', 32276), ('98.236.139.69', 35460), ('99.242.145.252', 50485), ('37.229.157.216', 51599), ('201.209.92.126', 30542), ('173.206.15.28', 63199)]



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

def array_to_string(arr):
    return ''.join(chr(x) for x in arr)

def xor_array(n1, n2):
    return [ord(n1[i]) ^ ord(n2[i]) for i,_ in enumerate(n1)]

def byte_array_to_uint(a):
  ret = 0
  for b in a:
    ret = ret * 256 + b
  return ret

def dht_dist(n1, n2):
    return byte_array_to_uint(xor_array(n1, n2))

#Returns a iterator that will iterate bit by bit over a string!
def string_bit_iterator(key):
    bitmask = 128 #1 << 7 or '0b10000000' 
    cur_char_index = 0

    while bitmask and cur_char_index < len(key):
        cur_key_char = ord(key[cur_char_index])

        if cur_key_char & bitmask:
            yield 1
        else:
            yield 0
         
        bitmask = bitmask >> 1
        if not bitmask:
            bitmask = 128 #1 << 7 or '0b10000000'
            cur_char_index = cur_char_index + 1

class DHTQuery(object):
    def __init__(self, msg, ip_port):
        self.msg = msg
        self.time_sent = time.time()
        self.ip_port = ip_port
        

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

    def __iter__(self):
        return string_bit_iterator(self.id)


class DHTBucket(object):
    __slots__ = ['key', 'value', 'left', 'right']
    def __init__(self, key, value):
        self.key = key
        self.value = value
        self.left = None
        self.right = None

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        ret_str = ""
        if self.value:
            ret_str += "V(%s)  " % self.value
        #if self.left:
        ret_str += "L(%s)  " % self.left
        #if self.right:
        ret_str += "R(%s)" % self.right
        
        return ret_str

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
        self._root = DHTBucket(None, None)
        self._add_branches_to_node(self._root)

        self.peer_id = peer_id
        self.bitmask = 1 << (20 * 8 - 1)    

    def _add_branches_to_node(self, node):
        node.left  = DHTBucket(0, [])
        node.right = DHTBucket(1, [])


    #Response for find_node, iterate down the tree
    #as far as possible to get a bucket to retunr
    #Takes a string of bytes (represnting a DHT Node ID)
    #Or a DHTPeer because it implements __iter__
    def get_target_bucket(self, target):
        if isinstance(target, basestring):
            key = string_bit_iterator(target)
        elif isinstance(target, DHTPeer):
            key = target
        else:
            print "Target must be either a string or DHTPeer type"
            return -1

        cur_node = self._root
        for b in key:
            if b:
                if cur_node.right:
                    cur_node = cur_node.right
                else:
                    return cur_node.value
            else:
                if cur_node.left:
                    cur_node = cur_node.left
                else:
                    return cur_node.value

        raise Exception("Fell off the bottom of the DHT routing tree.")

    def insert(self, dht_node):
        other_itr = dht_node.__iter__()
        my_iter = string_bit_iterator(self.peer_id)

        cur_node = self._root
        same_branch = True

        while cur_node != None:
            other_next_bit = other_itr.next()

            if same_branch:
                same_branch = not( my_iter.next() ^ other_next_bit)

            if other_next_bit:
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
                        cur_node.value[DHTTree.MAX_LIST_LENGTH - 1] = dht_node
                        print "After:%s" % str(cur_node.value)
                        break
                        pass #Check if last node is still valid, if not kcik off and add this one  
                else:
                    if dht_node not in cur_node.value:
                        cur_node.value.append(dht_node)  
                        break


class NodeListHeap(object):
    CONTACT_LIST_LENGTH = 5
    TIME_TILL_STALE = 60 * 10     #10 min
    def __init__(self, dht_node_id):
        self.dht_node_id = dht_node_id
        self.node_heap = []
        self.contacted = {}
        self.time_last_updated = 0

    def push(self, dht_peer):
        #Define a comparator that compares the distance of nodes' ids to my dht_node_id
        #def __cmp__(node_self, other):
        #    return int.__cmp__(dht_dist(self.dht_node_id, node_self.id), 
        #                       dht_dist(self.dht_node_id, other.id))

        #dht_peer.__cmp__ = lambda self, other
        for n in self.node_heap:
            if n[1] == dht_peer:
                return

        heappush(self.node_heap, (dht_dist(self.dht_node_id, dht_peer.id), dht_peer))
        self.time_last_updated = time.time()

    def contacted(self, dht_peer):
        self.contacted[dht_peer.id] = True

    def get_contact_list(self):
        return nsmallest(NodeListHeap.CONTACT_LIST_LENGTH, self.node_heap)


class DHT(object):
    
    INITIAL_BOOTSTRAP_DELAY = 1

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
        self.node_lists = {}

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.io_loop.add_handler(self.sock.fileno(), self.handle_input, self.io_loop.READ)
        self.bootstrap_delay = 10

        #Make a list of nodes to search for. This shoudl make it so my 
        #routing table has a wide variety of nodes
        self.current_bootstrap_node = 0

        self.bootstrapping_nodes = []
        self.bootstrapping_nodes.append(self.id)

        for byte in range(0,20):
            bitmask = 1 << 7
            bytes = [0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0]
            for bit in range(0,8):
                bytes[byte] = bitmask
                bitmask = bitmask >> 1
                self.bootstrapping_nodes.append(array_to_string(bytes))

    def bootstrap_by_finding_myself(self):
        target = self.bootstrapping_nodes[self.current_bootstrap_node]
        print "Bootstrapping to %s\n" % target

        try:
            self.find_node(target)
        except Exception, e:
            print str(e)
            self.io_loop.add_timeout(time.time() + self.bootstrap_delay, self.bootstrap_by_finding_myself)

        #XXX: The return  is temporary
        return


        self.current_bootstrap_node = self.current_bootstrap_node + 1
        if self.current_bootstrap_node >= len(self.bootstrapping_nodes):
            self.current_bootstrap_node = 0

        self.io_loop.add_timeout(time.time() + self.bootstrap_delay, self.bootstrap_by_finding_myself)

    def get_trasaction_id(self):
        self.transaction_id += 1

        if self.transaction_id >= 65534:
            self.transaction_id = 0
        
        return pack("H", self.transaction_id)

        #~~~~~~~~~~ MESSAGES define at http://www.bittorrent.org/beps/bep_0005.html

        #~~~~~~~~~~~~~~~~ MESSAGE: PING
        #ping Query = {"t":"aa", "y":"q", "q":"ping", "a":{"id":"abcdefghij0123456789"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}
    def ping(self, ip_port):
        print "PING ----%s--->\n" % str(ip_port)
        t_id = self.get_trasaction_id()
        ping_msg = {"t": t_id, "y": "q", "q": "ping", "a": {"id": self.id}}
        self.sock.sendto(bencode(ping_msg), ip_port)
        self.queries[t_id] = DHTQuery(ping_msg, ip_port)


    def got_ping_response(self, response):
        #add responder.id to my RoutingTable
        transaction_id = response["t"]
        q = self.queries[transaction_id]
        print "<----%s--- PONG\n" % str(q.ip_port)

        self.routing_table.insert(DHTPeer(response['r']['id'], q.ip_port))

        del self.queries[transaction_id]





        #~~~~~~~~~~~~~~~~ MESSAGE: find_node
        #find_node Query = {"t":"aa", "y":"q", "q":"find_node", "a": {"id":"abcdefghij0123456789", "target":"mnopqrstuvwxyz123456"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"0123456789abcdefghij", "nodes": "def456..."}}

        # TODO: I should timeout the NodeListHeap for a target. 
        #       Everytime I push somethign onto it update the imte
        #        Check eveyronce in a while and itme it out
    def find_node(self, target):
        #Find the bucket in the routing table for the target
        closest_bucket = self.routing_table.get_target_bucket(target)

        if not closest_bucket:
            raise Exception("There are no nodes in the routing table to send find node messages.")
        #Iterate over and find closest N nodes
        for n in closest_bucket:
            print "FIND NODE ----%s--->\n" % str(n.ip_port)
            t_id = self.get_trasaction_id()
            find_node_msg = {"t": t_id, "y": "q", "q": "find_node", "a": {"id": self.id, "target": target}}
            self.sock.sendto(bencode(find_node_msg), n.ip_port)
            self.queries[t_id] = DHTQuery(find_node_msg, n.ip_port)

        #    heappush(h, n)

        #Send find_node quereis to them
        #You could timeout some after a while 

        #If a response has the target them Im done, otherwise3
        #Do the list of peers in the responses, sorted by xor dist
        #Keep asking tthe top K nodes
        #When Your responses all come back, u have added them to the list,
        #and you have asked ALL top K nodes then u have the closes
        #nodes ur gonna get. Ur down. U just found the closest nodes.
        #Not the target

    def got_find_node_response(self, reponse):
        t_id = response["t"]
        q = self.queries[transaction_id]

        target_id = original_query['a']['id']

        if not self.node_lists.has_key(target_id):
            self.node_lists[target_id] = NodeListHeap(self.id)

        node_list = self.node_lists[target_id]

        node_list.push()
        

        #~~~~~~~~~~~~~~~~ MESSAGE: get_peers
        #get_peers Query = {"t":"aa", "y":"q", "q":"get_peers", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456"}}
        #Response with peers = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "values": ["axje.u", "idhtnm"]}}
        #Response with closest nodes = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "nodes": "def456..."}}
    def get_peers(self,reponseinfo_hash):
        pass

    def got_get_peers_response(self, reponse):
        pass

        #~~~~~~~~~~~~~~~~ MESSAGE: announce_peer
        #announce_peers Query = {"t":"aa", "y":"q", "q":"announce_peer", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456", "port": 6881, "token": "aoeusnth"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}
    def announce_peer(self, info_hash, port, token):
        pass

    def got_announce_peer_response(self, reponse):
        pass

    def handle_response(self, response):
        responder_id = response["r"]["id"]
        t_id = response["t"]

        if not self.queries.has_key(t_id):
            print "I dont have a transaction ID that matches this response"
            return

        original_query = self.queries[t_id].msg

        if original_query["q"] == "ping":
            self.got_ping_response(response)
        elif original_query["q"] == "find_node":
            print "~~~Got find_node Response\n"
            self.got_find_node_response(response)
        elif original_query["q"] == "get_peers":
            print "~~~Got get_peers Response\n"
            pass#self.got_get_peers_response(responder, original_query, response)
        elif original_query["q"] == "announce_peer":
            print "~~~Got announce_peer Response\n"
            pass#self.got_announce_peer_response(responder, original_query, response)

    def handle_query(self, bdict):
        pass

    def handle_input(self, fd, events):
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

    def clear_stale_state(self):
        #Clear old queries that never recieved a response
        #Clear old NodeListHeaps for searches that havent been updated
        pass

    #XXX: This could block on sock.sendto, maybe do non blocking
    def start(self):
        self.io_loop.add_timeout(time.time() + DHT.INITIAL_BOOTSTRAP_DELAY, self.bootstrap_by_finding_myself)

        for ip_port in self.ip_ports: 
            self.ping(ip_port)

        self.io_loop.start() 
        #distance(A,B) = |A xor B| Smaller values are closer.

if __name__ == "__main__":
    dht = DHT(51414, ip_ports)
    dht.start()

    import pdb; pdb.set_trace();













