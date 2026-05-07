#include <sys/param.h>
#include <sys/types.h>
#include <sys/fs/ufs_fs.h>

extern int around[9];
extern int inside[9];
extern u_char *fragtbl[];

void
fragacct(struct fs *fs, int fragmap, long fraglist[], int cnt)
{
    int inblk;
    int field;
    int subfield;
    int siz;
    int pos;

    inblk = (int)(fragtbl[fs->fs_frag][fragmap]) << 1;
    fragmap <<= 1;
    for (siz = 1; siz < fs->fs_frag; siz++) {
        if ((inblk & (1 << (siz + (fs->fs_frag % NBBY)))) == 0) {
            continue;
        }
        field = around[siz];
        subfield = inside[siz];
        for (pos = siz; pos <= fs->fs_frag; pos++) {
            if ((fragmap & field) == subfield) {
                fraglist[siz] += cnt;
                pos += siz;
                field <<= siz;
                subfield <<= siz;
            }
            field <<= 1;
            subfield <<= 1;
        }
    }
}