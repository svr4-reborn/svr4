# Clone STREAMS Driver

The `clone` driver under `uts/i386/io/clone.c` is not a hardware driver. It is the STREAMS clone-open multiplexer that turns a device open on the clone major into an open on another STREAMS-capable character driver.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/clone.c` |
| `mdev` record | `clone - Sciof cln 0 4 1 1 -1` |
| Character major | `4` |
| Handler prefix | `cln` |
| STREAMS export | `struct streamtab clninfo` |
| Static `node` metadata | clone-backed endpoint metadata lives in other modules’ `node` files |

## What The Driver Does

`clone` implements one central behavior: use the minor on the clone device as the major number of the real STREAMS device to open.

The comments at the top of `clnopen()` describe the flow directly:

1. Interpret the clone minor as the external major of the target device.
2. Translate that external major to the internal major.
3. Look up the target in `cdevsw[]`.
4. Swap the queue initializers over to the target driver’s `streamtab`.
5. Call the target device’s open routine with `CLONEOPEN`.
6. Replace the caller-visible device number with the real cloned result.

That behavior is why so many user-visible endpoints in this tree are declared as `clone ... c ...` in `node` metadata: the public node opens the clone driver, and clone-open dispatches to the target STREAMS entry in `cdevsw[]` when the target is configured.

## Endpoints That Depend On It

The source tree stages `clone` node metadata for several network and TLI entry points, including:

- `arp`
- `icmp`
- `ip`
- `llcloop`
- `rawip`
- `udp`
- `tcp`
- `ticlts`
- `ticots`
- `ticotsor`

Their historical `sdev` records are disabled, but the default AT386 generated configuration enables the network and TLI targets explicitly. These node records document the ABI shape that clone-open uses once the corresponding target modules are present in `cdevsw[]`. The TCP node metadata also declares a family of `inet/tcp*` names behind the clone path.

## Why It Matters

This driver is the boundary between:

- user-visible `/dev` names such as `tcp` or `udp`
- the clone major itself
- the real STREAMS endpoint that ultimately services the open

If a path exists in `node.d` but does not behave correctly at open time, `clone.c` is often the shortest route to understanding the failure.

## Related Files

- `uts/i386/master.d/clone/mdev`
- `uts/i386/master.d/arp/node`
- `uts/i386/master.d/icmp/node`
- `uts/i386/master.d/llcloop/node`
- `uts/i386/master.d/rawip/node`
- `uts/i386/master.d/tcp/node`
- `uts/i386/master.d/udp/node`
- `uts/i386/master.d/ip/node`
- `uts/i386/master.d/ticlts/node`
- `uts/i386/master.d/ticots/node`
- `uts/i386/master.d/ticotsor/node`