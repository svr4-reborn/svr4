# STREAMS Log Driver

The `log` driver in `uts/i386/io/log.c` is the STREAMS log driver. It collects messages emitted through the STREAMS logging path and exposes them through the log-related character-device nodes.

## Configuration Summary

| Field | Value |
| --- | --- |
| Source file | `uts/i386/io/log.c` |
| Handler prefix | `log` |
| Character major | `9` |
| Mask / Type | `-` / `fScio` |
| Configured units | `1` |
| Static node metadata | `log log c 5 0 0 444`; `log conslog c 0 0 0 222` |

## Current Role

- Collects kernel/STREAMS log traffic for consumers such as syslog-style tooling.
- Exposes both `log` and `conslog` names in the staged node metadata.
- Is part of the observability and administration surface rather than hardware IO.