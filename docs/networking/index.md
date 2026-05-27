# Networking System

This section documents the SVR4 networking stack as a complete system rather than as a set of individual drivers. The code under `uts/i386/netinet/` implements a STREAMS-based stack built from clone-backed endpoints, TPI and NPI messages, IPv4 demultiplexing, APP link convergence, and ARP address resolution.

The default AT386 kernel build now enables the networking and TLI endpoint modules through the modern `simple-idconfig-at386` path. The historical `master.d` `sdev` records for those modules remain `N`, and the reduced boot-floppy profile still excludes them, so these pages distinguish historical metadata from the generated default kernel.

The most important architectural point is that this is not a BSD-style kernel socket stack. BSD socket behavior is layered on top of STREAMS transport providers.

## Document Map

- [Diagrams](diagrams.md): one-page visual summary of the stack layers and the runtime send or receive flow.
- [Architecture](architecture.md): layers, message families, configured endpoints, and where state lives.
- [Socket And TLI Flow](socket-and-tli-flow.md): how BSD sockets, TLI, and KTLI setup sit on top of clone devices, `sockmod`, and `timod`.
- [TCP/IP Data Path](tcpip-data-path.md): runtime plumbing, outbound packet flow, inbound demultiplexing, and the passive-open path.

## High-Level Flow

When the relevant modules are configured and plumbed, the high-level flow is:

1. A user-visible endpoint such as `tcp`, `udp`, `rawip`, or `icmp` is opened through the clone driver.
2. The endpoint driver allocates protocol state and presents a TPI or NPI interface on its STREAMS queues.
3. `sockmod` adds BSD socket semantics on top of that endpoint; `timod` adds TLI or XTI semantics.
4. TCP, UDP, raw IP, and ICMP bind protocol numbers to the IP multiplexer.
5. IP routes packets to a lower provider and hands them through the APP module, which uses ARP when address resolution is needed before sending to the link driver.
6. Inbound IPv4 traffic reverses the packet path: link provider to APP to IP to the transport endpoint to `sockmod` or `timod` to user space. ARP traffic is handled by the paired ARP driver and cache.

## Relationship To The Per-Driver Notes

The driver pages under `docs/drivers/` still matter, especially for per-module summaries:

- [Clone STREAMS Driver](../drivers/clone.md)
- [ARP Endpoint](../drivers/arp.md)
- [ICMP Endpoint](../drivers/icmp.md)
- [IP Endpoint](../drivers/ip.md)
- [Raw IP Endpoint](../drivers/rawip.md)
- [TCP Endpoint](../drivers/tcp.md)
- [UDP Endpoint](../drivers/udp.md)
- [TICLTS](../drivers/ticlts.md)
- [TICOTS](../drivers/ticots.md)
- [TICOTSOR](../drivers/ticotsor.md)

Those pages describe the individual source-backed modules and endpoints. The networking pages here describe how they fit together into one end-to-end path when enabled.

## Current Tree Note

The current tree's `uts/i386/sys/socket.h` comments say that the old `socketsys` syscall entry is no longer exposed and point new code at `SIOCSOCKSYS`. However, no `SIOCSOCKSYS` handler was located under `uts/` while preparing these notes.

The historical user-space path is still visible in the original SVR4 libsocket sources: resolve a transport through `netconfig`, open the transport device, then push `sockmod`. That original flow matches the kernel layering documented in this section, so these notes describe the kernel architecture in terms of the evidenced STREAMS path rather than assuming an unlocated `SIOCSOCKSYS` implementation.