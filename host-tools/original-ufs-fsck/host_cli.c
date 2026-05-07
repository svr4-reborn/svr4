#include <sys/param.h>
#include <sys/types.h>
#include <sys/fs/ufs_fs.h>
#include <sys/vnode.h>
#include <sys/fs/ufs_inode.h>
#include "fsck.h"
#include "host_port.h"

static void
usage(void)
{
    fprintf(stderr, "usage: fsck-original-host [--offset-sectors N] [--write] [--yes|--no] [--preen] [--debug] [--trace-inode N] [--trace-sector N] image\n");
    exit(2);
}

void
fsck_host_init_defaults(void)
{
    nflag = 1;
    yflag = 0;
    preen = 0;
    debug = 0;
    bflag = SBLOCK;
    fsck_host_trace_inode = 0;
    fsck_host_trace_sector = -1;
    fsck_host_set_phase("startup");
    fsck_host_clear_current_inode();
    fsck_host_clear_read_context();
}

void
fsck_host_parse_options(int argc, char **argv, struct fsck_host_options *options)
{
    int index;

    options->image_path = 0;
    options->sector_offset = 0;

    for (index = 1; index < argc; index++) {
        if (strcmp(argv[index], "--offset-sectors") == 0) {
            if (index + 1 >= argc) {
                usage();
            }
            options->sector_offset = strtol(argv[++index], NULL, 0);
            continue;
        }
        if (strcmp(argv[index], "--write") == 0) {
            nflag = 0;
            continue;
        }
        if (strcmp(argv[index], "--yes") == 0) {
            yflag = 1;
            nflag = 0;
            continue;
        }
        if (strcmp(argv[index], "--no") == 0) {
            nflag = 1;
            yflag = 0;
            continue;
        }
        if (strcmp(argv[index], "--preen") == 0) {
            preen = 1;
            continue;
        }
        if (strcmp(argv[index], "--debug") == 0) {
            debug = 1;
            continue;
        }
        if (strcmp(argv[index], "--trace-inode") == 0) {
            if (index + 1 >= argc) {
                usage();
            }
            fsck_host_trace_inode = (ino_t)strtoul(argv[++index], NULL, 0);
            continue;
        }
        if (strcmp(argv[index], "--trace-sector") == 0) {
            if (index + 1 >= argc) {
                usage();
            }
            fsck_host_trace_sector = strtol(argv[++index], NULL, 0);
            continue;
        }
        if (argv[index][0] == '-') {
            usage();
        }
        options->image_path = argv[index];
    }

    if (options->image_path == 0) {
        usage();
    }
}