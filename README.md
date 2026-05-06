# SVR4-Remastered

This is a project to play around with the source code of UNIX SVR4, basically.

The future end-goal is to derive a usable operating system from it using a modern userspace, including a port of a modern C library (mlibc) and the works.
Right now, the kernel (`uts`) does compile, and can boot the minimal rootfs in ramdisk that exists from the boot install floppy (provide your own under a folder called `original_diskettes` for the build system to be able to create this).

# Building

This project uses a custom build system. It is quite basic and stupid, and kinda vibecoded, but it does work right now. You'll want to create a python venv and install the packages under `requirements.txt` for it to work. It uses the system compiler, I haven't made a cross-compiler yet.

Provide a boot diskette image under `original_diskettes/Base 01 (2.1a).img` and run the following to compile it:

```sh
python3 build.py -t boot-floppy-at386
```

This should create a boot floppy under `build/boot-media/base01-boot.img`. Most kernel drivers are at present excluded from this image, including the hard drive driver `hd`, but it does load userspace.

Other potentially useful build targets include:
- `boot-floppy-hybrid-at386` makes a image containing our bootloader and the original kernel under `{builddir}/boot-media/base01-hybrid.img`
- `kernel-system-at386` builds the complete kernel, closer to what you'd run on a installed system.

# Documentation

Still need to work on that. What little exists right now is under `docs/`, beware of the Clanker writing style though.

# Present list of what needs to be done

In no particular order:

- The build system is kinda garbage. In the far future, where self-hosting can be considered, it not only brings in Python as a dependency (not the end of the world), but also doesn't really make it possible to relink the kernel on system. This is a issue since that is how kernel modules are handled
  - Splitting `kernel.yaml` into multiple files would be a good start on cleaning up the build spec
- On the topic of build systems and modules, probably should find a way to create a HD image as a build target, with some valid rootfs
  - The above would be easier with a old-UFS FUSE driver that has proper write support and all that
- On the topic of userspace, a userspace bootstrap tree with xbstrap or jinx would be a good idea
- I can almost guarantee the code still has a trillion spots in it that are likely broken due to modern compilers interacting with code that has a tendency to use old stuff.
- Perhaps a clang format file? A part of me wants to fix things up fully first before I reformat all that, but I'm not sure lol
- Removing the old Makefiles and stuff when everything works to clean the repo up would also be a good idea, right now there are still there as reference