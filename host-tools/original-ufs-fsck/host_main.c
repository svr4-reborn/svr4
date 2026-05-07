#include <sys/param.h>
#include <sys/types.h>
#include <sys/fs/ufs_fs.h>
#include <sys/vnode.h>
#include <sys/fs/ufs_inode.h>
#include "fsck.h"
#include "host_port.h"

static void
checkfilesys(char *filesys)
{
    daddr_t n_ffree;
    daddr_t n_bfree;

    mountedfs = 0;
    if ((devname = setup(filesys)) == 0) {
        pfatal("CAN'T CHECK FILE SYSTEM.");
        exit(36);
    }
    if (!preen) {
        printf("** Last Mounted on %s\n", sblock.fs_fsmnt);
        printf("** Phase 1 - Check Blocks and Sizes\n");
    }
    fsck_host_set_phase("pass1");
    pass1();
    if (duplist) {
        printf("** Phase 1b - Rescan For More DUPS\n");
        fsck_host_set_phase("pass1b");
        pass1b();
    }
    if (!preen) {
        printf("** Phase 2 - Check Pathnames\n");
    }
    fsck_host_set_phase("pass2");
    pass2();
    if (!preen) {
        printf("** Phase 3 - Check Connectivity\n");
    }
    fsck_host_set_phase("pass3");
    pass3();
    if (!preen) {
        printf("** Phase 4 - Check Reference Counts\n");
    }
    fsck_host_set_phase("pass4");
    pass4();
    if (!preen) {
        printf("** Phase 5 - Check Cyl groups\n");
    }
    fsck_host_set_phase("pass5");
    pass5();
    fsck_host_set_phase("cleanup");

    n_ffree = sblock.fs_cstotal.cs_nffree;
    n_bfree = sblock.fs_cstotal.cs_nbfree;
    pwarn("%d files, %d used, %d free ",
        n_files, n_blks, n_ffree + sblock.fs_frag * n_bfree);
    if (preen) {
        printf("\n");
    }
    pwarn("(%d frags, %d blocks, %.1f%% fragmentation)\n",
        n_ffree, n_bfree, (float)(n_ffree * 100) / sblock.fs_dsize);

    if (dfile.mod) {
        fixstate = 1;
    } else {
        fixstate = 0;
    }
    if (fixstate) {
        (void)time(&sblock.fs_time);
        sblock.fs_state = FSOKAY - (long)sblock.fs_time;
        sbdirty();
    }
    ckfini();
    free(blockmap);
    free(statemap);
    free((char *)lncntp);
    if (dfile.mod) {
        printf("\n***** FILE SYSTEM WAS MODIFIED *****\n");
    }
}

int
main(int argc, char **argv)
{
    struct fsck_host_options options;

    fsck_host_init_defaults();
    fsck_host_parse_options(argc, argv, &options);
    host_slice_byte_offset = (long long)options.sector_offset * (long long)DEV_BSIZE;
    checkfilesys(options.image_path);
    return (exitstat);
}