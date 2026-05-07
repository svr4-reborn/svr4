#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_STAT_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_STAT_H

#include <sys/types.h>

struct stat {
	dev_t st_dev;
	dev_t st_rdev;
	mode_t st_mode;
};

extern int stat(const char *path, struct stat *buffer);

#endif