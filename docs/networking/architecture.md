# Networking Architecture

The networking code in this tree is a layered STREAMS system. The layers are separated by message families rather than by direct function-call APIs.

## Major Layers

| Layer | Primary code | Role |
| --- | --- | --- |
| Clone-open dispatch | `uts/i386/io/clone.c` | Turns opens on clone-backed node names such as `tcp` and `udp` into opens on the real STREAMS endpoint. |
| BSD socket compatibility | `uts/i386/io/sockmod.c` | Adds socket-style state, ioctls, address caching, listen handling, and shutdown semantics on top of TPI transports. |
| TLI and XTI compatibility | `uts/i386/io/timod.c` | Adds the generic TLI state machine and ioctl handling used by TLI and XTI callers, and by KTLI setup paths while the module is present. |
| Transport endpoints | `uts/i386/netinet/tcp_main.c`, `udp_main.c`, `raw_ip_main.c`, `ip_icmp.c` | Implement transport-specific open, close, state transitions, and protocol handoff to IP. |
| Shared IPv4 endpoint policy | `uts/i386/netinet/in_pcb.c` | Owns bind and connect policy, local and remote address selection, and protocol control blocks for TCP, UDP, and ICMP endpoints. Raw IP uses raw-specific bind and connect helpers while still storing address state in an `inpcb`. |
| IPv4 multiplexer | `uts/i386/netinet/ip_main.c`, `ip_input.c`, `ip_output.c` | Binds protocol numbers, routes packets, fragments and reassembles datagrams, and demultiplexes inbound traffic. |
| APP and ARP convergence | `uts/i386/netinet/app.c`, `arp.c` | APP is the STREAMS module on the IP-to-link packet path, while ARP is the paired protocol/control driver that resolves IPv4 addresses and manages the resolution cache. |
| Link providers | DLPI or LLC-style providers under `uts/` and `uts/add-ons/` | Carry actual frame transmission and reception below the APP and ARP boundary. |

## Message Families Between Layers

Each layer boundary uses a different protocol family of STREAMS messages.

| Boundary | Message family | Examples |
| --- | --- | --- |
| Socket or TLI surface to transport endpoint | TPI | `T_INFO_REQ`, `T_BIND_REQ`, `T_CONN_REQ`, `T_UNITDATA_REQ`, `T_CONN_IND` |
| Transport endpoint to IP | NPI | `N_BIND_REQ`, `N_UNBIND_REQ`, `N_UNITDATA_REQ`, `N_UNITDATA_IND` |
| IP-to-APP and APP-to-link provider | DLPI | `DL_BIND_REQ`, `DL_UNBIND_REQ`, `DL_UNITDATA_REQ`, `DL_UNITDATA_IND` |

This separation is why `sockmod`, `timod`, TCP, UDP, and IP each maintain their own state machines and translation logic.

## Source-Backed Endpoint Types

The main IPv4-facing endpoint implementations are clone-backed STREAMS devices declared under `uts/i386/master.d/`. Their source and `node` metadata are present in this tree, and the default AT386 generated configuration enables them even though the historical `sdev` records still say `N`. The table describes the endpoint types used by the STREAMS networking stack once runtime plumbing links the providers together.

| Endpoint | Clone node metadata | Default generated state | Service model |
| --- | --- | --- | --- |
| `ip` | `clone ip c ip` | Enabled; historical `sdev` is `N` | Network-layer multiplexor, not a socket-style transport |
| `tcp` | `clone tcp c tcp` plus `inet/tcp*` aliases | Enabled; historical `sdev` is `N` | `T_COTS_ORD` |
| `udp` | `clone udp c udp` | Enabled; historical `sdev` is `N` | `T_CLTS` |
| `rawip` | `clone rawip c rawip` | Enabled; historical `sdev` is `N` | `T_CLTS` |
| `icmp` | `clone icmp c icmp` | Enabled; historical `sdev` is `N` | `T_CLTS` |

The service types come from the providers' TPI `T_INFO_ACK` handling. TCP advertises ordered connection-oriented service, while UDP, raw IP, and ICMP advertise connectionless datagram service.

## Where State Lives

There is no single socket object that owns all network state.

Instead, state is split across layers:

- `sockmod` keeps socket-facing state such as `so_state`, cached local and peer addresses, socket options, and shutdown state.
- `timod` keeps generic TLI state machine state for callers using TLI or XTI directly.
- `inpcb` structures keep IPv4 endpoint state such as local and remote addresses, ports where the protocol has them, routing cache, and protocol options.
- `tcpcb` structures keep TCP-specific connection state such as sequence numbers, retransmit timers, accept queues, and queued outbound data.
- IP keeps lower-provider state in `provider[]` and upper-protocol bindings in `ip_protox[]`.
- APP keeps per-interface convergence state in `app_pcb[]`; ARP keeps protocol-side state in `arp_pcb[]` and the ARP cache. The paired structures link to each other for each interface.

Because state is split this way, debugging usually means identifying which layer owns the current decision rather than following one monolithic socket structure.

## Runtime Plumbing Model

When the networking modules are enabled, the stack is assembled at runtime with STREAMS links.

The important links are:

1. A lower link provider is linked under IP.
2. IP binds itself to the Ethernet IP SAP on that lower provider.
3. TCP, UDP, raw IP, and ICMP are linked under IP and each bind a protocol number such as `IPPROTO_TCP` or `IPPROTO_UDP`.
4. IP records those bindings in `ip_protox[]` so inbound datagrams can be delivered to the right upper endpoint. A raw IP binding to `IPPROTO_RAW` also fills otherwise unclaimed protocol slots as a fallback.
5. APP is pushed on the IP packet path at the IP-to-link boundary. It formats local link destinations and calls ARP when a cached mapping is missing; the paired ARP driver handles ARP packets and cache updates.

The result is a dynamically plumbed stack rather than a fixed compile-time call graph.

## Socket Surface Versus Native Surface

The native kernel networking surface here is TLI or TPI, not BSD sockets.

That distinction matters in two places:

- User-space BSD sockets depend on `sockmod` to translate socket operations into TPI requests and to translate TPI indications back into socket behavior.
- Kernel consumers can use KTLI helpers such as `t_kopen()`, which push `timod` when it is missing so setup can use TLI-style operations. Some in-kernel clients, including RPC/NFS paths, pop `timod` afterward and send directly to the transport stream for runtime traffic.

This is why the stack has both `sockmod` and `timod`: they are parallel shims over the same transport providers, but they serve different upper interfaces.