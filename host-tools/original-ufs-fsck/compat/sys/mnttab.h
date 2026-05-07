#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_MNTTAB_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_MNTTAB_H

struct mnttab {
    char *mnt_special;
    char *mnt_mountp;
    char *mnt_fstype;
    char *mnt_mntopts;
    char *mnt_time;
};

#endif