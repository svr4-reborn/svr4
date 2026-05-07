#include <sys/param.h>
#include <sys/types.h>
#include <sys/fs/ufs_fs.h>
#include <sys/vnode.h>
#include <sys/fs/ufs_inode.h>
#include "fsck.h"
extern int mflag;
static void badsb(char *s);

char *
setup(char *dev)
{
    daddr_t super;
    int index;
    int summary_index;
    long size;
    BUFAREA asblk;
    static char devstr[MAXPATHLEN];
#define altsblock asblk.b_un.b_fs

    strcpy(devstr, dev);
    devname = devstr;
    rawflg = 1;
    mountedfs = 0;

    dfile.rfdes = open(devstr, O_RDONLY);
    if (dfile.rfdes < 0) {
        printf("Can't open %s\n", devstr);
        return (0);
    }
    if (nflag) {
        dfile.wfdes = -1;
    } else {
        dfile.wfdes = open(devstr, O_RDWR);
        if (dfile.wfdes < 0) {
            printf("%s (NO WRITE)\n", devstr);
        }
    }
    dfile.mod = 0;
    lfdir = 0;
    super = bflag ? bflag : SBLOCK;
    initbarea(&sblk);
    initbarea(&fileblk);
    initbarea(&inoblk);
    initbarea(&cgblk);
    initbarea(&asblk);
    if (bread(&dfile, (char *)&sblock, super, (long)SBSIZE) != 0) {
        return (0);
    }
    sblk.b_bno = super;
    sblk.b_size = SBSIZE;
    if (sblock.fs_magic != FS_MAGIC) {
        badsb("MAGIC NUMBER WRONG");
        return (0);
    }
    if (sblock.fs_ncg < 1) {
        badsb("NCG OUT OF RANGE");
        return (0);
    }
    if (sblock.fs_cpg < 1 || sblock.fs_cpg > MAXCPG) {
        badsb("CPG OUT OF RANGE");
        return (0);
    }
    if (sblock.fs_ncg * sblock.fs_cpg < sblock.fs_ncyl ||
        (sblock.fs_ncg - 1) * sblock.fs_cpg >= sblock.fs_ncyl) {
        badsb("NCYL DOES NOT JIVE WITH NCG*CPG");
        return (0);
    }
    if (sblock.fs_sbsize > SBSIZE) {
        badsb("SIZE PREPOSTEROUSLY LARGE");
        return (0);
    }
    if (mflag) {
        return (devstr);
    }
    if (bflag == 0) {
        getblk(&asblk, cgsblock(&sblock, sblock.fs_ncg - 1), sblock.fs_sbsize);
        if (asblk.b_errs != 0) {
            return (0);
        }
        altsblock.fs_link = sblock.fs_link;
        altsblock.fs_rlink = sblock.fs_rlink;
        altsblock.fs_time = sblock.fs_time;
        altsblock.fs_cstotal = sblock.fs_cstotal;
        altsblock.fs_cgrotor = sblock.fs_cgrotor;
        altsblock.fs_fmod = sblock.fs_fmod;
        altsblock.fs_clean = sblock.fs_clean;
        altsblock.fs_ronly = sblock.fs_ronly;
        altsblock.fs_flags = sblock.fs_flags;
        altsblock.fs_maxcontig = sblock.fs_maxcontig;
        altsblock.fs_minfree = sblock.fs_minfree;
        altsblock.fs_optim = sblock.fs_optim;
        altsblock.fs_rotdelay = sblock.fs_rotdelay;
        altsblock.fs_maxbpg = sblock.fs_maxbpg;
        altsblock.fs_state = sblock.fs_state;
        bcopy((char *)sblock.fs_csp, (char *)altsblock.fs_csp, sizeof sblock.fs_csp);
        bcopy((char *)sblock.fs_fsmnt, (char *)altsblock.fs_fsmnt, sizeof sblock.fs_fsmnt);
        if (bcmp((char *)&sblock, (char *)&altsblock, (int)sblock.fs_sbsize) != 0) {
            badsb("TRASHED VALUES IN SUPER BLOCK");
            return (0);
        }
    }

    fmax = sblock.fs_size;
    imax = sblock.fs_ncg * sblock.fs_ipg;
    for (index = 0, summary_index = 0; index < sblock.fs_cssize; index += sblock.fs_bsize, summary_index++) {
        size = sblock.fs_cssize - index < sblock.fs_bsize ? sblock.fs_cssize - index : sblock.fs_bsize;
        sblock.fs_csp[summary_index] = (struct csum *)calloc(1, (unsigned)size);
        if (sblock.fs_csp[summary_index] == NULL) {
            goto badsb_cleanup;
        }
        if (bread(&dfile, (char *)sblock.fs_csp[summary_index],
            fsbtodb(&sblock, sblock.fs_csaddr + summary_index * sblock.fs_frag),
            size) != 0) {
            goto badsb_cleanup;
        }
    }

    bmapsz = roundup(howmany(fmax, NBBY), sizeof(short));
    blockmap = calloc((unsigned)bmapsz, sizeof(char));
    statemap = calloc((unsigned)(imax + 1), sizeof(char));
    lncntp = (short *)calloc((unsigned)(imax + 1), sizeof(short));
    if (blockmap == NULL || statemap == NULL || lncntp == NULL) {
        goto badsb_cleanup;
    }
    return (devstr);

badsb_cleanup:
    ckfini();
    return (0);
#undef altsblock
}

static void
badsb(char *s)
{
    printf("BAD SUPER BLOCK: %s\n", s);
}