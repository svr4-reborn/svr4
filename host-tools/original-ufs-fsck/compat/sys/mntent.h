#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_MNTENT_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_MNTENT_H

#include <strings.h>

#define MNTTAB "/etc/mnttab"
#define MNTTYPE_UFS "ufs"
#define MNTOPT_RO "ro"

struct mnttab;

extern int getmntent(FILE *fp, struct mnttab *mnt);
extern char *hasmntopt(struct mnttab *mnt, char *opt);

#endif