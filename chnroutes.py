#!/usr/bin/env python

import argparse
import math
import re
import subprocess
import sys
import urllib2

def generate_ovpn(metric):
    results = fetch_ip_data()

    upscript_header = """\
#!/bin/bash -

OLDGW=$(ip route show 0/0 | head -n1 | grep 'via' | grep -Po '\d+\.\d+\.\d+\.\d+')

ip -batch - <<EOF
"""
    downscript_header = """\
#!/bin/bash -

ip -batch - <<EOF
"""

    upfile = open('vpn-up.sh', 'w')
    downfile = open('vpn-down.sh', 'w')

    upfile.write(upscript_header)
    downfile.write(downscript_header)

    for ip, _, mask in results:
        upfile.write('route add %s/%s via $OLDGW metric %s\n' % (ip, mask, metric))
        downfile.write('route del %s/%s\n' % (ip, mask))

    upfile.write('EOF\n')
    downfile.write('EOF\n')

    upfile.close()
    downfile.close()

def generate_old(metric):
    results = fetch_ip_data()

    rfile = open('routes.txt','w')

    rfile.write('max-routes %d\n\n' % (len(results) + 20))

    for ip, mask, _ in results:
        rfile.write("route %s %s net_gateway %d\n" % (ip, mask, metric))

    rfile.close()

def generate_linux(metric):
    results = fetch_ip_data()

    upscript_header = """\
#!/bin/bash -

OLDGW=$(ip route show 0/0 | head -n1 | grep 'via' | grep -Po '\d+\.\d+\.\d+\.\d+')

if [ $OLDGW == '' ]; then
    exit 0
fi

if [ ! -e /tmp/vpn_oldgw ]; then
    echo $OLDGW > /tmp/vpn_oldgw
fi

ip -batch - <<EOF
"""

    downscript_header = """\
#!/bin/bash
export PATH="/bin:/sbin:/usr/sbin:/usr/bin"

OLDGW=$(cat /tmp/vpn_oldgw)

ip -batch - <<EOF
"""

    upfile = open('ip-pre-up', 'w')
    downfile = open('ip-down', 'w')

    upfile.write(upscript_header)
    downfile.write(downscript_header)

    for ip, _, mask in results:
        upfile.write('route add %s/%s via $OLDGW metric %s\n' % (ip, mask, metric))
        downfile.write('route del %s/%s\n' % (ip, mask))

    upfile.write('EOF\n')
    downfile.write('''\
EOF

rm /tmp/vpn_oldgw
''')

def generate_mac(metric):
    results=fetch_ip_data()

    upscript_header = """\
#!/bin/sh
export PATH="/bin:/sbin:/usr/sbin:/usr/bin"

OLDGW=`netstat -nr | grep '^default' | grep -v 'ppp' | sed 's/default *\\([0-9\.]*\\) .*/\\1/'`

if [ ! -e /tmp/pptp_oldgw ]; then
    echo "${OLDGW}" > /tmp/pptp_oldgw
fi

dscacheutil -flushcache
"""

    downscript_header = """\
#!/bin/sh
export PATH="/bin:/sbin:/usr/sbin:/usr/bin"

if [ ! -e /tmp/pptp_oldgw ]; then
        exit 0
fi

OLDGW=`cat /tmp/pptp_oldgw`
"""

    upfile = open('ip-up','w')
    downfile = open('ip-down','w')

    upfile.write(upscript_header)
    downfile.write(downscript_header)

    for ip, _, mask in results:
        upfile.write('route add %s/%s "${OLDGW}"\n' % (ip, mask))
        downfile.write('route delete %s/%s ${OLDGW}\n' % (ip, mask))

    downfile.write('\n\nrm /tmp/pptp_oldgw\n')
    upfile.close()
    downfile.close()

def generate_win(metric):
    results = fetch_ip_data()

    upscript_header = """\
@echo off
for /F "tokens=3" %%* in ('route print ^| findstr "\\<0.0.0.0\\>"') do set "gw=%%*"
"""

    upfile = open('vpnup.bat','w')
    downfile = open('vpndown.bat','w')

    upfile.write(upscript_header)
    upfile.write('ipconfig /flushdns\n\n')

    downfile.write("@echo off")
    downfile.write('\n')

    for ip, mask, _ in results:
        upfile.write('route add %s mask %s %s metric %d\n' % (ip, mask, "%gw%", metric))
        downfile.write('route delete %s\n' % ip)

    upfile.close()
    downfile.close()

def fetch_ip_data():
    url = 'http://ftp.apnic.net/apnic/stats/apnic/delegated-apnic-latest'
    try:
        data = subprocess.check_output(['wget', url, '-O-'])
    except (OSError, AttributeError):
        print >>sys.stderr, "Fetching data from apnic.net, it might take a few minutes, please wait..."
        data = urllib2.urlopen(url).read()

    cnregex = re.compile(r'apnic\|cn\|ipv4\|[0-9\.]+\|[0-9]+\|[0-9]+\|a.*', re.IGNORECASE)
    cndata = cnregex.findall(data)

    results = []

    for item in cndata:
        unit_items = item.split('|')
        starting_ip = unit_items[3]
        num_ip = int(unit_items[4])

        imask = 0xffffffff ^ (num_ip - 1)
        #convert to string
        imask = hex(imask)[2:]
        mask = [0] * 4
        mask[0] = imask[0:2]
        mask[1] = imask[2:4]
        mask[2] = imask[4:6]
        mask[3] = imask[6:8]

        #convert str to int
        mask = [int(i, 16) for i in mask]
        mask = "%d.%d.%d.%d" % tuple(mask)

        #mask in *nix format
        mask2 = 32 - int(math.log(num_ip, 2))

        results.append((starting_ip, mask, mask2))

    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Generate routing rules for vpn.")
    parser.add_argument('-p','--platform',
                        dest='platform',
                        default='openvpn',
                        nargs='?',
                        help="Target platform, it can be openvpn, old,  mac, linux, win. openvpn by default.")
    parser.add_argument('-m','--metric',
                        dest='metric',
                        default=5,
                        nargs='?',
                        type=int,
                        help="Metric setting for the route rules")

    args = parser.parse_args()

    if args.platform.lower() == 'openvpn':
        generate_ovpn(args.metric)
    elif args.platform.lower() == 'old':
        generate_old(args.metric)
    elif args.platform.lower() == 'linux':
        generate_linux(args.metric)
    elif args.platform.lower() == 'mac':
        generate_mac(args.metric)
    elif args.platform.lower() == 'win':
        generate_win(args.metric)
    else:
        print >>sys.stderr, "Platform %s is not supported." % args.platform
        exit(1)
