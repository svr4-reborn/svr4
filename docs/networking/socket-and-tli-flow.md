# Socket And TLI Flow

This page documents the upper half of the networking path: how a user-visible socket or TLI endpoint turns into a STREAMS transport endpoint inside the kernel.

## Historical BSD Socket Open Path

The original SVR4 libsocket sources show the canonical socket-open sequence:

1. `socket()` maps `(family, type, protocol)` to a `netconfig` entry.
2. The chosen `netconfig` entry provides the device name to open, such as a clone-backed TCP or UDP endpoint.
3. `_s_open()` opens that device, pushes `sockmod` if it is not already present, and synchronizes user-space state with `sockmod` through `SI_GETUDATA`.
4. If the caller requested a concrete protocol number, libsocket passes it with `SO_PROTOTYPE`.

That design explains why the socket layer here is split across:

- the original libsocket code that chooses a transport device
- the clone driver that redirects the open
- `sockmod`, which adds BSD socket semantics
- the actual transport endpoint, which still speaks TPI underneath

## What Clone Open Does

The clone driver is the first kernel-visible step for most user-facing network endpoints.

Its job is simple: interpret the clone minor as the real target major, swap in that target's STREAMS `streamtab`, and call the target open routine with `CLONEOPEN`.

That is why the staged networking node metadata declares clone-backed names such as:

- `clone tcp c tcp`
- `clone udp c udp`
- `clone ip c ip`
- `clone rawip c rawip`
- `clone icmp c icmp`

The actual endpoint open routines then allocate protocol state.

## What `sockmod` Adds

`sockmod` is the BSD socket compatibility shim.

On open, `sockmodopen()`:

1. Allocates a `so_so` slot.
2. Sends `T_INFO_REQ` downstream.
3. Waits for the provider's `T_INFO_ACK`.
4. Copies provider capabilities such as address size, TIDU size, and service type into `si_udata`.
5. Allocates local and peer address buffers.
6. Sets stream-head options for message handling.

After that, `sockmod` owns the BSD-socket-facing state for that stream: cached addresses, option bookkeeping, shutdown state, and connected or bound flags.

## Socket Operations To TPI Mapping

The important socket operations turn into TPI requests or `sockmod` control ioctls.

| Socket-style operation | Upper translation | Downstream effect |
| --- | --- | --- |
| `socket()` | Open transport endpoint, push `sockmod` | Provider open plus `T_INFO_REQ` |
| `bind()` | `TI_BIND` or `T_BIND_REQ` | TCP, UDP, and ICMP call `in_pcbbind()`; raw IP calls `rip_bind()` |
| `listen()` | `SI_LISTEN` | `sockmod` may synthesize unbind and rebind to set backlog correctly |
| `connect()` | `T_CONN_REQ` | TCP, UDP, and ICMP call `in_pcbconnect()`; raw IP calls `rip_connaddr()` |
| `send()` on a connected stream | Plain `M_DATA` or `T_DATA_REQ` path | TCP queues data or UDP emits a connected datagram |
| `sendto()` or datagram send | `T_UNITDATA_REQ` | UDP, raw IP, or ICMP sends a connectionless datagram |
| `recv()` | `sockmod` forwards `M_DATA` or `T_UNITDATA_IND` | User sees stream bytes or datagram payloads |
| `getsockname()` | `TI_GETMYNAME` | Provider query or `sockmod` cached-address fallback |
| `getpeername()` | `TI_GETPEERNAME` | Provider query or `sockmod` cached-address fallback |
| `shutdown()` | `SI_SHUTDOWN` | `sockmod` sets send and receive shutdown state and may emit flush or disconnect traffic |

For UNIX-domain special cases, `sockmod` keeps extra naming metadata and can service name ioctls without asking the provider.

## Bind, Connect, And Listen Flow

Most IPv4 transports do not duplicate the whole address policy themselves. TCP, UDP, and ICMP delegate bind and connect work to the shared `inpcb` helpers. Raw IP still stores address state in its `inpcb`, but its TPI bind and connect requests use raw-specific helpers because raw IP has no transport port policy.

The usual flow is:

1. `sockmod` or a TLI caller emits `T_BIND_REQ` or `T_CONN_REQ`.
2. TCP, UDP, raw IP, or ICMP validate TPI state.
3. TCP, UDP, and ICMP call `in_pcbbind()` or `in_pcbconnect()`.
4. Raw IP calls `rip_bind()` or `rip_connaddr()`.
5. The selected helper validates local or remote addresses, chooses a source address when needed, and updates the `inpcb`. For TCP, UDP, and ICMP, the shared helper also owns port selection and port conflict checks.
6. The transport replies with the matching TPI acknowledgement or confirmation.

`listen()` is slightly different because backlog belongs to the transport, not just the `inpcb`:

1. `sockmod` receives `SI_LISTEN`.
2. If the endpoint is not yet bound, it converts the request into a bind with a connection-indication count.
3. If the endpoint is already bound and backlog must change, it issues an unbind followed by a new bind so the transport sees the updated backlog.
4. TCP records the backlog in `t_qlimit` and marks the endpoint as accepting connections.

## Accept And Passive Open

The passive-open path is split between TCP and `sockmod`.

1. A listening TCP endpoint receives a SYN.
2. TCP allocates a child `inpcb` and `tcpcb` with `inpnewconn()`.
3. The child starts in the incomplete-connection queue `t_q0`.
4. Once the handshake completes, TCP moves the child to the completed queue `t_q` and emits `T_CONN_IND` upstream.
5. The socket-compatibility layer can then service `accept()` semantics using that completed connection indication.

So the accept queue is native TCP state, while the socket API is a compatibility view layered over the same queue transitions.

## Receive-Side Translation

The receive side depends on the provider service type:

- `T_COTS_ORD` transports such as TCP mostly deliver stream data as `M_DATA` plus connection, disconnect, and orderly-release indications.
- `T_CLTS` transports such as UDP, raw IP, and ICMP deliver payloads as `T_UNITDATA_IND` records containing a source address.

`sockmodrput()` converts those provider messages into BSD-socket-facing behavior. It also maintains cached local and peer addresses, tracks pending errors, and enforces shutdown state.

## TLI And KTLI Path

TLI and KTLI use the same transport endpoints as the socket path, but they do not use `sockmod`.

`timod` is the TLI/XTI compatibility shim. User-space TLI and XTI callers use it directly, and `t_kopen()` pushes it when a KTLI setup path opens a transport without it. Some in-kernel consumers then pop `timod` and send directly to the transport stream for runtime traffic, so it is not guaranteed to remain in every KTLI path.

That path is:

1. Open the transport endpoint.
2. Push `timod` for TLI or XTI, or let `t_kopen()` push it during KTLI setup if it is missing.
3. Use TLI or KTLI calls such as `t_kbind()`, `t_kconnect()`, and `t_kunbind()`.
4. Let `timod` enforce the generic TLI state machine while it is present.

The KTLI helpers under `uts/i386/ktli/` use that setup model, but kernel clients are allowed to keep or remove `timod` according to their runtime needs.

## Current Tree Note About `SIOCSOCKSYS`

The current tree defines `SIOCSOCKSYS` and comments that the old `socketsys` syscall slot is gone. However, no matching `SIOCSOCKSYS` handler was found under `uts/` while these notes were assembled.

For now, the fully evidenced socket flow remains the historical one from the original libsocket sources: pick a transport through `netconfig`, open that transport, push `sockmod`, then use the socket-compatibility operations documented above.