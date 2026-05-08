This is the SVr4-reborn UNIX System V distribution/OS/kernel/whatever you can call it.
The userland is based on a modern FOSS stack, but the kernel is obviously ancient. You may find that not everything always works as you intend.

The goal of this project is to continue development on SVr4 as if it were a modern project.
If you find any issues or bugs, please file issues at: https://github.com/svr4-reborn/svr4/issues
Suggestions should go into the discussion tab instead: https://github.com/svr4-reborn/svr4/discussions

---- What will not be part of the project ----
For the moment, a container-eqsue way to run old UNIX software.
I do not intend to break syscall compatability, so that shouldn't ever break something, but for the moment, I'm not going out of my way to maintain any semblence of ABI compatabilty outside that

Do not expect this project to run your favourite classic UNIX apps, even less since this is based on the AT&T UNIX System V Release 4 kernel, and I'm not aware of *that* much software written for specifically this and not UnixWare or other variants.
