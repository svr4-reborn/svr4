#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_TYPES_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_TYPES_H

#include <stddef.h>
#include <stdint.h>

typedef signed char int8_t;
typedef unsigned char u_int8_t;
typedef short int int16_t;
typedef unsigned short int u_int16_t;
typedef int int32_t;
typedef unsigned int u_int32_t;
typedef long long int64_t;
typedef unsigned long long u_int64_t;

typedef unsigned int uint_t;
typedef unsigned short ushort_t;
typedef unsigned char uchar_t;
typedef unsigned long ulong_t;

typedef unsigned int uid_t;
typedef unsigned int gid_t;
typedef int pid_t;
typedef unsigned int mode_t;
typedef unsigned int dev_t;
typedef unsigned int ino_t;
typedef long off_t;
typedef int ssize_t;

typedef char *addr_t;
typedef char *caddr_t;
typedef long daddr_t;
typedef short cnt_t;
typedef ulong_t paddr_t;
typedef uchar_t use_t;
typedef short sysid_t;
typedef short index_t;
typedef short lock_t;
typedef char *faddr_t;
typedef unsigned long k_sigset_t;
typedef unsigned long k_fltset_t;
typedef long id_t;
typedef unsigned long major_t;
typedef unsigned long minor_t;

typedef ushort_t o_mode_t;
typedef short o_dev_t;
typedef ushort_t o_uid_t;
typedef o_uid_t o_gid_t;
typedef short o_nlink_t;
typedef short o_pid_t;
typedef ushort_t o_ino_t;

typedef unsigned char unchar;
typedef unsigned short ushort;
typedef unsigned int uint;
typedef unsigned long ulong;

typedef unsigned char u_char;
typedef unsigned short u_short;
typedef unsigned int u_int;
typedef unsigned long u_long;
typedef struct _quad {
    long val[2];
} quad;

#endif