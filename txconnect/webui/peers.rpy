import simplejson as json
import pprint, cgi, urllib, os, datetime

from twisted.web.resource import Resource
from twisted.web.server import NOT_DONE_YET
from twisted.python import log
from twisted.application.service import IServiceCollection

from django.db.models import Sum, Count
from txconnect.queuestore import models
from txconnect import dbthread, humanreadable, django_templates
from txconnect.directconnect import interfaces
from txconnect.directconnect.peer import Peer

class PeersPage(Resource):
    isLeaf = True

    def render_GET(self, request):
        hubHerder = interfaces.IHubHerder(self.application)
        peerHerder = interfaces.IPeerHerder(self.application)
        
        peers = {}
        for hub in hubHerder.hubs.values():
            for peer, info in hub.peers.items():
                peers[peer] = info
        
        peers = peers.items()
        peers.sort(lambda aa, bb: cmp(aa[0].nick, bb[0].nick))
        
        waitingDCs = []
        for peer, dc in peerHerder._waitingToConnect.items():
            waitingDCs.append((peer, dc.active(), datetime.datetime.fromtimestamp(dc.getTime()),))
            
        c = {
          'peers': peers,
          'waitingPeers': peerHerder.waitingPeers,
          'waitingToConnect': peerHerder._waitingToConnect,
          'waitingDCs': waitingDCs,
        }

        return django_templates.render_string(TEMPLATE, c)

TEMPLATE = """
{% extends "simple.html" %}
{% block style %}
  .waiting {background-color: grey;}
  .active {background-color:sienna;}
  tr.even {background-color: #eee;}
  tr.odd {background-color: #fff;}
  tr.online {background-color: green;}
  table {width: 100%}
{% endblock %}

{% block content %}
<h1>{% block title %}peer status{% endblock %}</h1>
<table>
<thead>
 <tr>
   <th>nick</th>
   <th>client</th>
   <th>connected</th>
   <th>slots</th>
   <th>share</th>
 </tr>
</thead>
<tbody>
{% for peer, info in peers %}
  <tr class="{% if peer in waitingPeers %}waiting{% endif %}">
    <td>{{peer.nick}}</td>
    <td>{{info.client}} {{info.clientVersion}}</td>
    <td>{{info.connected|timesince}}</td>
    <td>{{info.openSlots}}</td>
    <td>{{info.shareSize|filesizeformat}}</td>
  </tr>
{% endfor %}
</tbody>
</table>
<table>
{% for peer, active, time in waitingDCs %}
<tr><td>{{peer}}</td><td>{{active}}</td><td>{% if active %}{{time|timeuntil}} until{% endif %}{% if not active %}{{time|timesince}} ago{% endif %}</td></tr>
{% endfor %}
</table>
{% endblock %}
"""

resource = PeersPage()
