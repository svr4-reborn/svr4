#include <stdio.h>
#include <string.h>

#include <sys/mnttab.h>
#include <sys/vfstab.h>

int
getmntent(FILE *fp, struct mnttab *mnt)
{
    (void)fp;
    (void)mnt;
    return (-1);
}

char *
hasmntopt(struct mnttab *mnt, char *opt)
{
    (void)mnt;
    (void)opt;
    return (0);
}

int
getvfsent(FILE *fp, struct vfstab *vfs)
{
    (void)fp;
    (void)vfs;
    return (-1);
}

char *
hasvfsopt(struct vfstab *vfs, char *opt)
{
    (void)vfs;
    (void)opt;
    return (0);
}

char *
unrawname(char *name)
{
    return (name);
}