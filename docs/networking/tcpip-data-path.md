# TCP/IP Data Path

This page documents the lower half of the stack: how the configured transport endpoints are linked into IP, how IP reaches the link layer, and how packets move through the stack in both directions.

## Runtime Plumbing

When the source-backed networking modules are enabled, the IPv4 stack is assembled with STREAMS links.

### Lower links under IP

When a lower provider is linked under IP, `ipioctl()`:

1. Allocates a free `provider[]` slot.
2. Records the lower queue pointer and link index.
3. Marks the provider as an IPv4-facing interface.
4. Sends `DL_BIND_REQ` for the IP SAP.

That initial link gives IP a bank of lower-provider queue pointers for output. Provider details are filled in across the rest of the control path: `DL_INFO_ACK` supplies MTU limits, while the interface ioctl path maintains addresses, flags, metrics, and routes.

### Upper links above IP

When TCP, UDP, raw IP, or ICMP are linked below to IP, their ioctl handlers send `N_BIND_REQ` for the relevant protocol number:

- TCP binds `IPPROTO_TCP`.
- UDP binds `IPPROTO_UDP`.
- raw IP binds `IPPROTO_RAW`.
- ICMP binds `IPPROTO_ICMP`.

IP records those bindings in `ip_protox[]`. That table is the main inbound demultiplexor from IPv4 protocol number to upper STREAMS endpoint.

The raw IP binding has a special extra effect: when raw IP binds `IPPROTO_RAW`, IP fills currently unclaimed `ip_protox[]` slots with the raw-IP endpoint. A protocol number with no explicit TCP, UDP, ICMP, or other binding can therefore still be delivered to raw IP while that fallback binding is present.

## Outbound Flow

## Connected TCP Send

The normal connected TCP send path is:

1. User space writes to the stream.
2. `sockmod` verifies that the endpoint is connected and forwards the data.
3. `tcp_state()` queues data onto the TCP send queue.
4. `tcp_output()` builds the combined TCP and IP header, computes checksums, and emits an `N_UNITDATA_REQ` aimed at IP.
5. `ip_output()` chooses a route and lower provider, fills in source address and IPv4 header fields, fragments if needed, and rewrites the request as `DL_UNITDATA_REQ` for the lower layer.
6. APP resolves the final link-layer destination through ARP when necessary and hands the frame to the lower driver.

The important consequence is that TCP never talks directly to Ethernet or to a NIC driver. It only knows how to hand IPv4 packets to the IP multiplexer.

## UDP Send

UDP follows the same lower path once it has produced a datagram.

There are two common entry cases:

- Connected UDP send: `M_DATA` reaches `udp_state()`, which calls `udp_output()` using the endpoint's connected peer.
- Unconnected datagram send: `T_UNITDATA_REQ` carries the destination address, and `udp_state()` calls `udp_output()` with a temporary address selection.

From `udp_output()` onward, the path is the same pattern as TCP:

1. Build UDP and IPv4 headers.
2. Wrap the datagram in `N_UNITDATA_REQ`.
3. Hand it to IP.
4. Let `ip_output()` route, fragment if required, and produce `DL_UNITDATA_REQ` for the lower layer.

## Raw IP And ICMP Send

Raw IP and ICMP are also `T_CLTS` transports, but their send paths are not just UDP with different headers.

Raw IP handles connected `T_DATA_REQ` and unconnected `T_UNITDATA_REQ` by queueing the request and calling `rip_output()`. For unconnected sends, it temporarily records the destination with `rip_connaddr()`, emits the packet, and then disconnects the raw endpoint. `rip_output()` builds an IPv4 header using the endpoint protocol and wraps the packet in `N_UNITDATA_REQ` for IP.

ICMP handles connected `T_DATA_REQ` and unconnected `T_UNITDATA_REQ` in `ip_icmp.c`. The unconnected path temporarily connects through the shared IPv4 helper, calls `icmp_output()`, and then disconnects. `icmp_output()` builds the ICMP/IP header and sends the packet down to IP with `IPPROTO_ICMP`.

## IP Output Details

`ip_output()` is where IPv4-specific transmission policy lives.

It is responsible for:

- applying IP options when present
- choosing the outgoing provider from routing state or direct-interface routing
- selecting a source address if none was fixed yet
- checking broadcast permissions
- fragmenting oversized packets unless `IP_DF` forbids it
- computing the IPv4 header checksum

Once that work is complete, the packet leaves IP as `DL_UNITDATA_REQ` rather than as an IP-specific message.

## ARP And APP Boundary

The lower handoff from IP is not directly to a NIC driver.

`app.c` and `arp.c` document the actual arrangement: APP is a STREAMS module on the IP-to-link packet path, while ARP is the paired protocol/control driver for address resolution and cache maintenance. APP receives the `DL_UNITDATA_REQ` carrying the IPv4 destination, calls `arpresolve()` if needed, and only then emits the final frame to the lower device.

APP and ARP keep separate per-interface control blocks and link them by interface name. That pairing lets APP call into ARP resolution state for outbound IPv4 traffic, while the ARP driver receives ARP packets and updates the shared cache.

If the ARP cache does not yet contain the destination mapping:

1. `arpresolve()` holds the packet.
2. `arpwhohas()` sends an ARP request.
3. When the reply arrives, the held packet is released and transmitted.

This is why the IP layer can express its destination as an IPv4 address at the DLPI boundary even though the hardware driver ultimately needs a link-layer address.

## Inbound Flow

## Link Provider To IP

Inbound packets climb the stack in reverse order:

1. The lower provider emits data up the linked stream. IPv4 packets climb through the APP module toward IP, while ARP packets climb through the paired ARP stream.
2. APP passes the DLPI indication and IPv4 payload toward IP; ARP consumes ARP traffic and updates the resolution cache.
3. IP receives IPv4 datagrams through its lower read side and drops the DLPI wrapper before validating the IP header.

## IP Reassembly And Demultiplexing

`ipintr()` performs the key IPv4 receive steps:

1. Validate the packet.
2. Reassemble fragments if the datagram arrived fragmented.
3. Look up the destination upper endpoint in `ip_protox[]` using `ip_p`.
4. Wrap the packet in `N_UNITDATA_IND`.
5. Deliver it to the upper endpoint queue recorded in `ip_pcb[]`.

If the protocol number still maps to the unbound sentinel in `ip_protox[]`, IP drops the packet. If raw IP is bound as the `IPPROTO_RAW` fallback, otherwise unclaimed protocol numbers map to raw IP instead.

## UDP Receive

When UDP receives an inbound packet:

1. `udp_input()` verifies header length and checksum.
2. UDP looks up the destination endpoint with `in_pcblookup()`.
3. If no endpoint matches, UDP may generate an ICMP port-unreachable error.
4. If a match exists, UDP strips the headers, builds `T_UNITDATA_IND` with the source address, and delivers the payload upstream.

That is why UDP receive appears as a datagram indication rather than as plain stream bytes.

## TCP Receive And Connection Setup

TCP receive is more stateful.

For established traffic:

1. `tcp_input()` validates the segment and updates the TCP state machine.
2. Acknowledgements trim queued send data.
3. In-order payload is queued for the upper stream.
4. Connection-state changes emit the matching TPI indications, such as disconnect or orderly release.

For passive open:

1. A listening endpoint is marked with `SO_ACCEPTCONN` and has a backlog in `t_qlimit`.
2. On SYN arrival, `tcp_input()` creates a child endpoint with `inpnewconn()`.
3. The child is placed on the incomplete queue `t_q0`.
4. Once the three-way handshake completes, `inpisconnected()` moves the child to the completed queue `t_q`.
5. `inpisconnected()` emits `T_CONN_IND` upstream on the listening endpoint.
6. The socket-compatibility layer can then satisfy `accept()` semantics from that completed connection indication.

The passive-open queueing therefore belongs to native TCP state, not to a separate BSD-socket layer.

## Where The Reverse Path Reaches User Space

The last translation step depends on the upper shim:

- `sockmod` turns transport indications into BSD-socket behavior.
- `timod` turns transport indications into TLI or XTI behavior.
- KTLI helpers use the same transport semantics inside the kernel. Some paths keep `timod`; others remove it after setup and talk directly to the transport stream.

So even though user space may think in terms of `socket()`, `listen()`, `accept()`, `send()`, and `recv()`, the actual receive-side path is still driven by TPI indications and STREAMS message queues all the way up to the compatibility module.

## Practical Debugging Boundaries

When tracing a failure, it usually helps to stop at one of these boundaries:

- Socket or TLI request translation in `sockmod` or `timod`
- IPv4 bind or connect policy in `in_pcb.c`, with raw-IP-specific bind and connect handling in `raw_ip_cb.c`
- Transport state in `tcp_state.c`, `tcp_input.c`, `udp_state.c`, or `udp_io.c`
- Protocol demultiplexing in `ip_main.c` and `ip_input.c`
- Route or provider selection in `ip_output.c`
- Address resolution in `arp.c` and final link handoff in `app.c`

Those boundaries align with the actual layer splits in this stack, so they are better debugging pivots than treating the whole network path as one monolithic subsystem.