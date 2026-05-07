#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_HOST_PORT_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_HOST_PORT_H

struct fsck_host_options {
    char *image_path;
    long sector_offset;
};

void fsck_host_init_defaults(void);
void fsck_host_parse_options(int argc, char **argv, struct fsck_host_options *options);
void fsck_host_set_phase(const char *phase);

#endif