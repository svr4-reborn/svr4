#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_VFSTAB_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_VFSTAB_H

#define VFSTAB "/etc/vfstab"
#define MNTTYPE_UFS "ufs"
#define MNTOPT_RO "ro"

struct vfstab {
    char *vfs_special;
    char *vfs_fsckdev;
    char *vfs_mountp;
    char *vfs_fstype;
    char *vfs_fsckpass;
    char *vfs_automnt;
    char *vfs_mntopts;
};

extern int getvfsent(FILE *fp, struct vfstab *vfs);
extern char *hasvfsopt(struct vfstab *vfs, char *opt);

#endif