import dht
import json
from functools import partial
from bencode import bdecode, bencode
from struct import *
import sys, re, random, thread, threading, os, re
import logging

import tornado.ioloop
from tornado import iostream

import tornado.options
from tornado.options import define, options
import tornado.web
import tornado.httpserver

class ComplexEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, dht.DHTPeer):
            return (obj.id.encode("hex"), obj.ip_port[0], obj.ip_port[1])
        else:
            return json.JSONEncoder.default(self, obj)

class IndexHandler(tornado.web.RequestHandler):
    @classmethod
    def register_dht(self, dht):
        self.dht = dht

    def get(self):

        def populate(tree, dict):
            if tree.left:
                dict['left'] = {}
                populate(tree.left, dict['left'])
            if tree.right:
                dict['right'] = {}
                populate(tree.right, dict['right'])
            if tree.value:
                dict['value'] = tree.value

            return dict

        rt = {}

        populate(self.dht.routing_table._root, rt)

        d = {'dht':str(self.dht),
             'boostrapping_nodes': len(self.dht.bootstrapping_nodes),
             'routing_table': str(self.dht.routing_table),
             'rt': rt
             }

        for id, n in self.dht.node_lists.iteritems():
            d["Node_List_%s" % id.encode("hex")] = n.get_debug_array()

        for id in self.dht.infohash_peers:
            d["Peers_for_%s" % id.encode("hex")] = self.dht.infohash_peers[id].keys()

        self.set_header('Content-Type','text/plain')
        self.write( json.dumps(d, indent=2, cls=ComplexEncoder ) )


if __name__ == "__main__":
    ioloop = tornado.ioloop.IOLoop()
    ioloop.install()

    define('debug',default=True, type=bool) # save file causes autoreload
    define('frontend_port',default=7070, type=int)

    tornado.options.parse_command_line()
    settings = dict( (k, v.value()) for k,v in options.items() )

    ip_ports =  [('202.177.254.130', 43251), ('71.7.233.108', 40641), ('189.223.55.147', 54037), ('186.213.54.11', 57479), ('85.245.177.29', 58042), ('2.81.68.199', 37263), ('188.24.193.27', 15796), ('210.252.33.4', 39118), ('175.143.215.38', 56067), ('95.42.100.15', 34278), ('211.224.26.47', 25628), ('92.6.154.240', 48783), ('173.255.163.104', 52159), ('2.10.206.61', 12815), ('187.123.98.253', 58901), ('83.134.13.212', 10770), ('78.139.207.123', 50045), ('125.25.191.209', 56548), ('71.234.82.146', 14973), ('72.207.74.219', 14884), ('79.136.190.188', 50634), ('72.80.103.198', 36823), ('77.122.72.44', 56554)]

    dht = dht.DHT(51414, ip_ports)

    frontend_routes = [
        ('/?', IndexHandler),
    ]
    frontend_application = tornado.web.Application(frontend_routes, **settings)
    frontend_server = tornado.httpserver.HTTPServer(frontend_application, io_loop=ioloop)
    frontend_server.bind(options.frontend_port, '')
    frontend_server.start()    

    IndexHandler.register_dht(dht)
    
    dht.bootstrap()
    dht.start()


