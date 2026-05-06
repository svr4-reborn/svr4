This repository contains a project to build, and in the future, modernise the classic UNIX System V Release 4 kernel. It is based on a old source code dump of that operating system, and at the moment, has minimal code changes applied to it.

Keep the following in mind when debugging:
- Most, if not all, of the code you'll find worked back in the day on the old SysV tooling. If something breaks, it is very likely to be related to modern tooling. Don't try to paper over such issues with small local code fixes if it is possible that it can be explained with either a tooling issue or issues arising due to changes in modern compilers. If code changes are needed, try to think about why you are doing them, and if fixing a local issue is correct if there is a chance that it is caused by something bigger, in such a situation, prefer fixing the bigger underlying issue, even if it is more work.
- The preferred debugging method is to use GDB and QEMUs GDB stub.

Keep the following in mind with the build system:
- The legacy Makefiles serve only as reference to how the kernel and OS were compiled back in the day. They are not used anymore.
- All build logic resides in the Python build tooling and the kernel build spec.

Keep the following in mind across the whole project:
- Most of the code you'll find is very old, and the style matches it. Until such time as I run clang-format over it, and decide a new coding style for all of it, try to match the style of code. This does *NOT* include leaving out return types, function argument types, or anything like that - the old code regularly lets the compiler imply return types of either `int` or `void`, and does the same with function arguments. If you have to add a new function for some reason, be explicit about both rather than following the outdated coding style in this exact way.
