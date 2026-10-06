"""Trip Orders - who may talk to the office web port. Two plain rules, no side effects:

* the HOST NAME in the request must be one of this PC's own addresses (stops DNS rebinding: a web site that points its own name at this PC);
* the PEER ADDRESS must be this PC itself or a private network: the office LAN, a company VPN or WAN. The program is never meant to be
  reachable from the internet; a request from a public address is refused even if a router or the firewall lets it through.
"""
import ipaddress
import re
import socket

# private and company-network ranges: RFC 1918, link-local, carrier-grade NAT (many VPNs), IPv6 unique-local and link-local
PRIVATE = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', '100.64.0.0/10', '127.0.0.0/8',
                                             'fc00::/7', 'fe80::/10', '::1/128')]
THIS_PC = ('127.0.0.1', '::1')


def parse_networks(items):
    """(networks, ignored): the networks of a config list such as ["192.168.1.0/24", "10.20.0.0/16"]; text that is not a network is returned in `ignored`."""
    nets, bad = [], []
    for it in items if isinstance(items, list) else []:
        try:
            nets.append(ipaddress.ip_network(str(it).strip(), strict=False))
        except ValueError:
            bad.append(str(it))
    return nets, bad


def peer_allowed(ip, networks=None):
    """May this client address connect? This PC itself always; otherwise an address inside `networks` (default: the private ranges above)."""
    try:
        a = ipaddress.ip_address(str(ip).split('%')[0])
    except ValueError:
        return False
    if getattr(a, 'ipv4_mapped', None):
        a = a.ipv4_mapped                       # ::ffff:192.168.1.5 is the IPv4 address 192.168.1.5
    if str(a) in THIS_PC:
        return True
    return any(a in n for n in (PRIVATE if networks is None else networks) if n.version == a.version)


def own_names(extra=()):
    """Lower-case names this PC is known by: computer name, its full name with the domain, and the configured extras."""
    names = {str(h).strip().lower().rstrip('.') for h in extra if str(h).strip()}
    for fn in (socket.gethostname, socket.getfqdn):
        try:
            names.add(fn().strip().lower().rstrip('.'))
        except OSError:
            pass
    return names


def host_allowed(header, names=()):
    """Is this Host header one of this PC's own addresses? Allowed: IP addresses, localhost, one-word computer names, *.local,
    and the lower-case `names` (own full name, configured company names)."""
    h = (header or '').strip()
    if not h or len(h) > 255 or not re.fullmatch(r'[A-Za-z0-9._\-:\[\]]+', h):
        return False
    if h.startswith('['):                       # [::1]:8090
        end = h.find(']')
        if end < 0 or not re.fullmatch(r'(:\d{1,5})?', h[end + 1:]):
            return False
        name = h[1:end]
    else:
        name, colon, port = h.partition(':')
        if colon and not re.fullmatch(r'\d{1,5}', port):
            return False
    name = name.lower().rstrip('.')
    if not name:
        return False
    try:
        ipaddress.ip_address(name)
        return True                             # a browser that connects to an IP address cannot be fooled by somebody else's name
    except ValueError:
        pass
    return '.' not in name or name.endswith('.local') or name in names
