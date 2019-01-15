#!/usr/bin/python
import sys
from string import Template
from defang import defang
from defang import refang
import os

from pyurlabuse import PyURLAbuse

from urllib.parse import quote
import rt
import requests

import logging
import sphinxapi

if len(sys.argv) < 4:
    print("Usage: %s Incident-ID Templatename URL [Onlinecheck:True|False] [Queue]" % sys.argv[0])
    sys.exit(1)

incident = sys.argv[1]
template = sys.argv[2]
url = sys.argv[3]
try:
    onlinecheck = sys.argv[4]
except Exception:
    onlinecheck = True
try:
    queue = sys.argv[5]
except Exception:
    queue = 5

mypath = os.path.dirname(os.path.realpath(sys.argv[0]))
template = os.path.join(mypath, template)


# Config
min_size = 5000
import config as cfg
ua = cfg.ua
rt_url = cfg.rt_url
rt_user = cfg.rt_user
rt_pass = cfg.rt_pass
sphinx_server = cfg.sphinx_server
sphinx_port = cfg.sphinx_port
excludelist = cfg.known_good_excludelist
debug = False


def is_online(resource):
    try:
        session = requests.Session()
        session.headers.update({'User-agent': ua})
        response = session.get(resource)
        size = len(response.content)
        if int(size) > min_size:
            return True, size
        else:
            return False, size
    except Exception as e:
        print(e)
        return False, -1


# RT
logger = logging.getLogger('rtkit')
tracker = rt.Rt(rt_url, rt_user, rt_pass)
tracker.login()

# Sphinx
client = sphinxapi.SphinxClient()
client.SetServer(sphinx_server, sphinx_port)
client.SetMatchMode(2)


def is_ticket_open(id):
    status = False
    try:
        response = tracker.get_ticket(id)
        ticket_status = response['Status']
        if ticket_status == "open" or ticket_status == "new":
            status = id
    except Exception:
        return False
    return status


def open_tickets_for_url(url):
    q = "\"%s\"" % url
    res = 0
    # tickets = []
    result = client.Query(q)
    for match in result['matches']:
        res = is_ticket_open(match['id'])
    return res


print("Checking URL: %s" % url)

if onlinecheck is True:
    open_tickets = open_tickets_for_url(url)
    if open_tickets > 0:
        print("Ticket for this URL (%s) already exists: %s" % (url, open_tickets))
        sys.exit(0)
    online, size = is_online(url)
    if not online:
        print("Resource %s is offline (size: %s)" % (url, size))
        sys.exit(1)

response = PyURLAbuse.run_query(url, digest=True)

emails = response['digest'][1]
asns = response['digest'][2]

text = defang(quote(response['digest']))
d = {'details': text}

try:
    f = open(template)
    subject = f.readline().rstrip()
    templatecontent = Template(f.read())
    body = templatecontent.substitute(d)
except Exception:
    print("Couldn't open template file (%s)" % template)
    sys.exit(1)
f.close()

# print emails
# emails = "sascha@rommelfangen.de"

subject = "%s (%s)" % (subject, "|".join(asns))
content = {
    'content': {
        'queue': queue,
        'requestor': emails,
        'subject': quote(subject),
        'text': body,
    }
}

if debug:
    sys.exit(42)

try:
    ticketid = tracker.create_ticket(**content)
    print("Ticket created: %s" % ticketid)
except rt.RtError as e:
    logger.error(e)


# update ticket link
content = {
    'content': {
        'memberof': incident,
    }
}
try:
    response = tracker.edit_ticket_links(ticketid, **content)
    logger.info(response)
except rt.RtError as e:
    logger.error(e)

tracker.logout()
