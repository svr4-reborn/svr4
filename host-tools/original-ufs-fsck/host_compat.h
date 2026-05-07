#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_HOST_COMPAT_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_HOST_COMPAT_H

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <errno.h>
#include <time.h>

#define getline fsck_getline

#ifndef O_RDONLY
#define O_RDONLY 0
#endif

#ifndef O_RDWR
#define O_RDWR 2
#endif

#ifndef howmany
#define howmany(x, y) (((x) + ((y) - 1)) / (y))
#endif

#ifndef roundup
#define roundup(x, y) ((((x) + ((y) - 1)) / (y)) * (y))
#endif

#ifndef WHIBYTE
#define WHIBYTE(status) (((status) >> 8) & 0xff)
#endif

extern long long host_slice_byte_offset;
extern ino_t fsck_host_trace_inode;
extern long fsck_host_trace_sector;
extern ino_t fsck_host_current_inode;
extern const char *fsck_host_current_phase;
extern const char *fsck_host_current_read_context;
extern int fsck_host_current_indirect_level;
extern int open(const char *path, int flags, ...);
extern int close(int fd);
extern int read(int fd, void *buf, unsigned int count);
extern int write(int fd, const void *buf, unsigned int count);
off_t fsck_host_lseek(int fd, off_t offset, int whence);
void fsck_host_set_current_inode(ino_t inumber);
void fsck_host_clear_current_inode(void);
void fsck_host_set_read_context(const char *context, int indirect_level);
void fsck_host_clear_read_context(void);
int fsck_host_should_trace_read(long sector);
void fsck_host_trace_read(const char *source, long sector, long size);

#define lseek fsck_host_lseek

#endif