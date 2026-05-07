#include <sys/param.h>
#include <sys/types.h>
#include <sys/fs/ufs_fs.h>
#include <sys/vnode.h>
#include <sys/fs/ufs_inode.h>
#include "fsck.h"

int mflag = 0;
char hotroot = 0;
int returntosingle = 0;
int rootfs = 0;
long long host_slice_byte_offset = 0;
ino_t fsck_host_trace_inode = 0;
long fsck_host_trace_sector = -1;
ino_t fsck_host_current_inode = 0;
const char *fsck_host_current_phase = "startup";
const char *fsck_host_current_read_context = "block";
int fsck_host_current_indirect_level = 0;

off_t
#undef lseek
fsck_host_lseek(int fd, off_t offset, int whence)
{
    if (whence == 0) {
        return lseek(fd, (off_t)(host_slice_byte_offset + (long long)offset), whence);
    }
    return lseek(fd, offset, whence);
}
#define lseek fsck_host_lseek

void
fsck_host_set_phase(const char *phase)
{
    if (phase == NULL) {
        phase = "unknown";
    }
    fsck_host_current_phase = phase;
}

void
fsck_host_set_current_inode(ino_t inumber)
{
    fsck_host_current_inode = inumber;
}

void
fsck_host_clear_current_inode(void)
{
    fsck_host_current_inode = 0;
}

void
fsck_host_set_read_context(const char *context, int indirect_level)
{
    if (context == NULL) {
        context = "block";
    }
    fsck_host_current_read_context = context;
    fsck_host_current_indirect_level = indirect_level;
}

void
fsck_host_clear_read_context(void)
{
    fsck_host_current_read_context = "block";
    fsck_host_current_indirect_level = 0;
}

int
fsck_host_should_trace_read(long sector)
{
    if (fsck_host_trace_inode >= UFSROOTINO &&
        fsck_host_current_inode == fsck_host_trace_inode) {
        return (1);
    }
    if (fsck_host_trace_sector >= 0 && sector == fsck_host_trace_sector) {
        return (1);
    }
    return (0);
}

void
fsck_host_trace_read(const char *source, long sector, long size)
{
    long long absolute_sector;

    if (!fsck_host_should_trace_read(sector)) {
        return;
    }
    absolute_sector = (host_slice_byte_offset / (long long)DEV_BSIZE) + (long long)sector;
    fprintf(stderr,
        "TRACE_READ phase=%s inode=%lu sector=%ld absolute_sector=%lld size=%ld source=%s context=%s indirect_level=%d\n",
        fsck_host_current_phase,
        (unsigned long)fsck_host_current_inode,
        (long)sector,
        absolute_sector,
        size,
        source,
        fsck_host_current_read_context,
        fsck_host_current_indirect_level);
}