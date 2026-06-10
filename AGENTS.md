This repository contains a project to build, and in the future, modernise the classic UNIX System V Release 4 kernel. It is based on a old source code dump of that operating system, and at the moment, has minimal code changes applied to it.

Keep the following in mind when debugging:
- Most, if not all, of the code you'll find worked back in the day on the old SysV tooling. If something breaks, it is very likely to be related to modern tooling. Don't try to paper over such issues with small local code fixes if it is possible that it can be explained with either a tooling issue or issues arising due to changes in modern compilers. If code changes are needed, try to think about why you are doing them, and if fixing a local issue is correct if there is a chance that it is caused by something bigger, in such a situation, prefer fixing the bigger underlying issue, even if it is more work.
- The preferred debugging method is to use GDB and QEMUs GDB stub.

Keep the following in mind with the build system:
- The legacy Makefiles serve only as reference to how the kernel and OS were compiled back in the day. They are not used anymore.
- All build logic resides in the Python build tooling and the kernel build spec.

Keep the following in mind when testing in a VM:
- Use the Jinx-backed make targets from the repository root. `make hdd` regenerates the hard-disk image at the build root, and `make qemu` boots it under QEMU *and* rebuilds the HDD image.
- Runtime checks can be done directly in that QEMU session. `make qemu` uses `-debugcon stdio`, so kernel/debug output appears in the terminal, but the interactive guest console is the QEMU display. If you need to drive the guest from the terminal, use `make qemu-curses`; it uses the curses VGA display and writes debug console output to `../svr4-build/qemu-debugcon.log` instead of stdio.
- After rebuilding and reinstalling changed packages into the sysroot, regenerate the image with `make hdd`, boot with `make qemu` or `make qemu-curses`, log in on the console, and run small utilities such as `ping 127.0.0.1` from inside the guest.
- If a package source under `extras/` changes, rebuild and install that package with Jinx (`cd ../svr4-build; ./jinx build package-name && ./jinx install -f sysroot package-name`) before `make hdd` or handing the conversation back to the user; the image target installs existing package outputs and does not necessarily rebuild changed package sources by itself.
- If you do not need to view the HDD contents or test it yourself (only test it yourself if you are asked to!), don't run `make hdd`, since when the user tests it with `make qemu` themselves, it will rebuild the image anyway.

Keep the following in mind across the whole project:
- Most of the code you'll find is very old, and the style matches it. Until such time as I run clang-format over it, and decide a new coding style for all of it, try to match the style of code. This does *NOT* include leaving out return types, function argument types, or anything like that - the old code regularly lets the compiler imply return types of either `int` or `void`, and does the same with function arguments. If you have to add a new function for some reason, be explicit about both rather than following the outdated coding style in this exact way.
