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
ip_ports = [('126.129.176.163', 58481), ('98.15.176.247', 34555), ('90.18.108.27', 14397), ('95.68.75.111', 37414), ('94.41.45.13', 31254), ('92.247.248.56', 21723), ('176.63.240.31', 43759), ('89.164.204.238', 33564), ('173.78.146.149', 18138), ('77.244.239.22', 57256), ('182.169.180.38', 60252), ('109.86.179.69', 29658), ('81.162.18.3', 36288), ('78.30.235.212', 10803), ('178.35.237.17', 19695), ('109.129.94.242', 47588), ('95.55.144.6', 46686), ('94.66.254.214', 64551), ('188.82.29.34', 18199), ('68.84.45.204', 38435), ('86.68.106.234', 54445),
('98.245.82.215', 27114), ('68.175.40.234', 32126), ('24.109.43.211', 49091), ('66.36.140.57', 31375), ('95.178.171.53', 45682), ('83.134.131.66', 45682), ('174.50.130.27', 41509), ('24.89.206.102', 29463), ('67.177.10.117', 12380), ('91.152.72.163', 44910), ('99.243.110.219', 14110), ('67.183.236.43', 46583), ('96.30.130.32', 28101)
]


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
def string_bit_iterator(str_to_iterate):
    bitmask = 128 #1 << 7 or '0b10000000' 
    cur_char_index = 0

    while cur_char_index < len(str_to_iterate):
        if bitmask & ord(str_to_iterate[cur_char_index]):
            yield 1
        else:
            yield 0
         
        bitmask = bitmask >> 1
        if bitmask == 0:
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

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return "ID:%s IP:%s PORT: %s" % (self.id, self.ip_port[0], self.ip_port[1])


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
    MAX_LIST_LENGTH = 8
    def __init__(self, dht):
        self._root = DHTBucket(None, None)
        self._add_branches_to_node(self._root)
        self.dht = dht
        self.peer_id = dht.id
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

        #This should iterate down the same side of a tree as the key provided.
        #It should then return up the list of nodes it finds. It then adds
        #nodes from the opposing branch from the bottom up until the list is
        #DHTTree.MAX_LIST_LENGTH long
        def search_tree(key, cur_node):
            try:
                b = key.next()
            except Exception, e:
                print "Fell off the bottom of the DHT routing tree."
                raise e

            next_node = cur_node[b]

            if not next_node:
                return cur_node.value
            else:   
                that_side = search_tree(key, next_node)
                if that_side and len(that_side) < DHTTree.MAX_LIST_LENGTH:
                    other_side_of_tree = cur_node[b ^ 1]
                    return that_side + search_tree(key, other_side_of_tree)
                else:
                    return that_side

        return search_tree(key, self._root)

    def find_non_responsive_node(self, current_list, new_node):
        def check_transactions(ping_transactions, new_node, current_list):
            for count, transaction_id in enumerate(ping_transactions):
                if self.dht.queries.has_key(transaction_id):
                    current_list[count] = new_node

        ping_transactions = []
        for n in current_list:
            ping_transactions.append(self.dht.ping(n.ip_port))

        self.dht.io_loop.add_timeout(time.time() + DHT.PONG_TIMEOUT, partial(check_transactions, ping_transactions, new_node, current_list))



    def insert(self, dht_node):
        other_itr = dht_node.__iter__()
        my_iter = string_bit_iterator(self.peer_id)

        cur_node = self._root
        same_branch = True

        while cur_node != None:
            other_next_bit = other_itr.next()

            if same_branch:
                same_branch = not( my_iter.next() ^ other_next_bit)

            cur_node = cur_node[other_next_bit]

            if cur_node and cur_node.value != None:
                if len(cur_node.value) >= DHTTree.MAX_LIST_LENGTH:
                    #import pdb; pdb.set_trace()
                    if same_branch:
                        nodes_to_re_add = cur_node.value
                        cur_node.value = None
                        self._add_branches_to_node(cur_node)
                        for n in nodes_to_re_add:
                            #print "Readding %s" % n
                            self.insert(n)
                        self.insert(dht_node)
                        #print "Done"
                        break
                    else:
                        #TODO I prob only want to ping all the nodes in a bucket every so many seconds
                        #I should add a line that checks this is only ran eery few seconds
                        #print "Before:%s" % str(cur_node.value)
                        self.find_non_responsive_node(cur_node.value, dht_node)
                        #print "After:%s" % str(cur_node.value)
                        break
                else:
                    if dht_node not in cur_node.value:
                        cur_node.value.append(dht_node)  
                        break


class NodeListHeap(object):
    CONTACT_LIST_LENGTH = 8
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

    def get_next_closest_nodes(self):
        return [i[1] for i in nsmallest(NodeListHeap.CONTACT_LIST_LENGTH, self.node_heap)]


class DHT(object):
    INITIAL_BOOTSTRAP_DELAY = 1
    NODE_ID_IP_PORT_LENGTH = 26
    PONG_TIMEOUT = 5
    IP_PORT_LENGTH = 6
    def __init__(self, port, bootstrap_ip_ports, node_id = None, io_loop = None):
        self.transaction_id = 0
        self.ip_ports = bootstrap_ip_ports

        if not node_id:
            self.id = gen_peer_id()
        else:
            self.id = node_id

        self.routing_table = DHTTree(self)

        self.port = port
        self.io_loop = io_loop or ioloop.IOLoop.instance()

        self.queries = {}
        self.node_lists = {}

        self.infohash_peers = {}

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
        #return


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
        return t_id


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
            raise Exception("TODO: Fix get_target_bucket, make it get something. There are no nodes in the routing table to send find node messages.")
        #Iterate over and find closest N nodes
        for n in closest_bucket:
            self.send_find_node_message(target, n.ip_port)

    def send_find_node_message(self, target, ip_port):
        print "FIND NODE ----%s--->\n" % str(ip_port)
        t_id = self.get_trasaction_id()
        find_node_msg = {"t": t_id, "y": "q", "q": "find_node", "a": {"id": self.id, "target": target}}
        self.sock.sendto(bencode(find_node_msg), ip_port)
        self.queries[t_id] = DHTQuery(find_node_msg, ip_port)

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

    def got_find_node_response(self, response):
        #print "Got find_node response"
        target_id = self.get_target_id_from_response(response)
        print "<----%s--- FIND_NODES \n" % target_id

        if response['r'].has_key('nodes'):
            #print "The response has nodes"
            self.add_nodes_to_heap(response, target_id)

            messaged_a_node = False
            for ip_port in self.iterate_closest_nodes(target_id):
                messaged_a_node = True
                self.send_find_node_message(target_id, ip_port)

            #if not messaged_a_node: #TODO and all or some find_nodes messages have gotten responses or timed out
            #    print "\n\n!!!!!!!!You have found all the closest nodes to %s!!!!!!!!\n\n" % target_id
        else:
            print "Response for find_node has no nodes:\n%s" % str(response)

        #print str(self.routing_table._root)

    def get_target_id_from_response(self, response):
        transaction_id = response["t"]
        original_query = self.queries[transaction_id].msg
        return original_query['a']['target']

    def get_info_hash_from_response(self, response):
        transaction_id = response["t"]
        original_query = self.queries[transaction_id].msg
        return original_query['a']['info_hash']        

    def add_nodes_to_heap(self, response, target_id):
        if not self.node_lists.has_key(target_id):
            self.node_lists[target_id] = NodeListHeap(self.id)

        node_list = self.node_lists[target_id]
        nodes_and_ip_port_str = response['r']['nodes']
        number_of_nodes = len(nodes_and_ip_port_str)/DHT.NODE_ID_IP_PORT_LENGTH

        #print "Adding %s node to heap" % number_of_nodes

        for cur_node in range(0, number_of_nodes):
            base_str_index = cur_node * DHT.NODE_ID_IP_PORT_LENGTH
            cur_node_id_ip_port_str = nodes_and_ip_port_str[base_str_index:base_str_index + DHT.NODE_ID_IP_PORT_LENGTH]
            id_bytes, ip_bytes, port = unpack(">20s4sH",  cur_node_id_ip_port_str)
            ip_str = '.'.join(map(str, map(ord, ip_bytes)))
            #print "Adding node:%s (%s:%s)" % (id_bytes, ip_str, port)
            new_node = DHTPeer(id_bytes, (ip_str, port))
            node_list.push(new_node)
            self.routing_table.insert(new_node)
            
            #TODO Check if new node is the one im looking for?!

    def iterate_closest_nodes(self, target_id):
        node_list = self.node_lists[target_id]
        for n in node_list.get_next_closest_nodes():
            if not node_list.contacted.has_key(n.id):
                node_list.contacted[n.id] = True
                yield n.ip_port
                

        #~~~~~~~~~~~~~~~~ MESSAGE: get_peers
        #get_peers Query = {"t":"aa", "y":"q", "q":"get_peers", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456"}}
        #Response with peers = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "values": ["axje.u", "idhtnm"]}}
        #Response with closest nodes = {"t":"aa", "y":"r", "r": {"id":"abcdefghij0123456789", "token":"aoeusnth", "nodes": "def456..."}}
    def get_peers(self, info_hash):
        #Find the bucket in the routing table for the target
        closest_bucket = self.routing_table.get_target_bucket(info_hash)

        if not closest_bucket:
            raise Exception("TODO: Fix get_target_bucket, make it get something. There are no nodes in the routing table to send find node messages.")
        #Iterate over and find closest N nodes
        for n in closest_bucket:
            self.send_get_peers_message(info_hash, n.ip_port)


    def send_get_peers_message(self, info_hash, ip_port):       
        print "GET PEERS ----%s--->\n" % str(ip_port)
        trasaction_id = self.get_trasaction_id()
        get_peers_msg = {"t": trasaction_id, "y": "q", "q": "get_peers", "a": {"id": self.id, "info_hash": info_hash}}
        self.sock.sendto(bencode(get_peers_msg), ip_port)
        self.queries[trasaction_id] = DHTQuery(get_peers_msg, ip_port)


    def got_get_peers_response(self, response):
        #print "Got get_peers response"
        target_id = self.get_info_hash_from_response(response)
        print "<----%s--- GET_PEERS \n" % target_id

        if response['r'].has_key('nodes'):
            #print "The get_peers response has nodes"
            self.add_nodes_to_heap(response, target_id)

            messaged_a_node = False
            for ip_port in self.iterate_closest_nodes(target_id):
                messaged_a_node = True
                self.send_get_peers_message(target_id, ip_port)

            #if not messaged_a_node: #TODO and all or some find_nodes messages have gotten responses or timed out
            #    print "\n\n!!!!!!!!You have found all the closest nodes to %s!!!!!!!!\n\n" % target_id
        elif response['r'].has_key('values'):
            import pdb; pdb.set_trace()
            #print "\n\n!!!!The get_peers has values!!!!\n\n"
            self.add_peers_to_list(response, target_id)        
        else:
            print "Response for find_node has no nodes:\n%s" % str(response)

        #print str(self.routing_table._root)

    def add_peers_to_list(self, response, target_id):
        if not self.infohash_peers.has_key(target_id):
            self.infohash_peers[target_id] = {}

        peer_ip_port_strs = response['r']['values']

        #print "Got a list of %d peers" % len(peer_ip_port_strs)

        for ip_port_str in peer_ip_port_strs:
            ip_bytes, port = unpack(">4sH",  ip_port_str)
            ip_str = '.'.join(map(str, map(ord, ip_bytes)))

            self.infohash_peers[target_id][(ip_str, port)] = time.time()     

        #print "Peer list for hash:%s is:\n%s" % (target_id, str(self.infohash_peers[target_id]))   


        #~~~~~~~~~~~~~~~~ MESSAGE: announce_peer
        #announce_peers Query = {"t":"aa", "y":"q", "q":"announce_peer", "a": {"id":"abcdefghij0123456789", "info_hash":"mnopqrstuvwxyz123456", "port": 6881, "token": "aoeusnth"}}
        #Response = {"t":"aa", "y":"r", "r": {"id":"mnopqrstuvwxyz123456"}}
    def announce_peer(self, info_hash, port, token):
        print "ANNOUNCE_PEER ----%s--->\n" % str(ip_port)
        

    def got_announce_peer_response(self, response):
        target_id = self.get_target_id_from_response(response)
        print "<----%s--- ANNOUNCE_PEER \n" % target_id
        

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
            self.got_get_peers_response(response)
        elif original_query["q"] == "announce_peer":
            print "~~~Got announce_peer Response\n"
            self.got_announce_peer_response(response)

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


    def get_peers_test(self):
        target_id = "0670DCEF46F9F9C7E5F980EA23F9EA441BD7F00F".decode("hex")
        print "\n\n\nGet Peers for %s\n\n\n" % target_id
        self.get_peers(target_id)
        self.io_loop.add_timeout(time.time() + 5, self.get_peers_test)

    #XXX: This could block on sock.sendto, maybe do non blocking
    def start(self):
        self.io_loop.add_timeout(time.time() + DHT.INITIAL_BOOTSTRAP_DELAY, self.bootstrap_by_finding_myself)

        #self.io_loop.add_timeout(time.time() + 15, self.get_peers_test)

        for ip_port in self.ip_ports: 
            self.ping(ip_port)

        self.io_loop.start() 
        #distance(A,B) = |A xor B| Smaller values are closer.

if __name__ == "__main__":
    dht = DHT(51414, ip_ports)
    dht.start()

    import pdb; pdb.set_trace();













