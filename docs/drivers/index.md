# Per-Driver Notes

This section collects focused notes for individual drivers instead of keeping everything in the top-level kernel docs.

The current coverage includes the active default AT386 device catalog and the source-backed networking or TLI metadata that the STREAMS networking notes depend on. Several network and TLI endpoints have historical `sdev` records set to `N`, but the default generated kernel now enables them through the modern build spec while the reduced boot-floppy profile excludes them.

## Hardware And Console

- [AT Hard Disk Driver](hd.md)
- [AT Floppy Disk Driver](fd.md)
- [Memory Special-File Driver](mem.md)
- [CMOS RAM Driver](cram.md)
- [Asynchronous Serial Driver](asy.md)
- [Line Printer Driver](lp.md)
- [Real-Time Clock Driver](rtc.md)
- [Keyboard/Display Driver](kd.md)
- [Keyboard/Display Video Mapper](kdvm.md)
- [Generic Video Dispatcher](gvid.md)

## Pseudo Devices And Legacy Plumbing

- [Clone STREAMS Driver](clone.md)
- [Channel Multiplexer Driver](cmux.md)
- [Kernel Profiler Driver](prf.md)
- [STREAMS Log Driver](log.md)
- [Pseudo-Terminal Master Driver](ptm.md)
- [Pseudo-Terminal Slave Driver](pts.md)
- [XT Packet Protocol Driver](xt.md)
- [Shell Layers Driver](sxt.md)
- [Generic TTY Driver](gentty.md)
- [Operating System Messages Driver](osm.md)
- [System Message Driver](sysmsg.md)
- [STREAMS Administrative Driver](sad.md)
- [NXT Windowing Terminal Driver](nxt.md)
- [NSXT Shell Layers Multiplexor](nsxt.md)

## STREAMS Modules

- [ANSI Parser Module](ansi.md)
- [APP Link-Convergence Module](app.md)
- [Character Translation Module](char.md)
- [Connection Establishment Module](connld.md)
- [Terminal Line Discipline Module](ldterm.md)
- [Pipe Flush Module](pipemod.md)
- [Socket Compatibility Module](sockmod.md)
- [TLI Compatibility Module](timod.md)
- [TTY Compatibility Module](ttcompat.md)

The terminal and pipe modules in this section are part of the current default AT386 device catalog. `app`, `sockmod`, and `timod` are included here because the networking documentation depends on them; their historical `sdev` entries are disabled, but the default generated kernel enables them explicitly.

## Clone-Backed Network And TLI Endpoints

- [ARP Endpoint](arp.md)
- [ICMP Endpoint](icmp.md)
- [IP Endpoint](ip.md)
- [LLC Loopback Endpoint](llcloop.md)
- [Raw IP Endpoint](rawip.md)
- [TCP Endpoint](tcp.md)
- [UDP Endpoint](udp.md)
- [TLI Connectionless Endpoint](ticlts.md)
- [TLI Connection-Oriented Endpoint](ticots.md)
- [TLI Orderly-Release Endpoint](ticotsor.md)

These pages are intentionally source-backed and conservative. They document what the current tree and generated configuration say, not what later SVR4 variants may have added.

## Relationship To The Other Pages

- [Kernel Device Drivers](../kernel-drivers.md) explains the modern build path, `master.d` metadata, and the switch-table generation rules.
- [Block And Character Device Catalog](../kernel-device-catalog.md) gives the default AT386 inventory across all configured drivers.

## Coverage Limits

- This section follows the current default AT386 catalog plus explicitly documented source-backed networking metadata, not the entire historical tree.
- Add-on drivers under `uts/add-ons/` still remain outside this section until they are integrated into the default modern build path.