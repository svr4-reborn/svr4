#include <fcntl.h>
#include <stdio.h>
#include <sys/stat.h>
#include <sys/sysmacros.h>
#include <sys/types.h>
#include <sys/ioctl.h>
#include <stropts.h>
#include <termios.h>
#include <unistd.h>
#include <stdlib.h>

#define SAD_SAP (('D' << 8) | 0x01)
#define SAP_RANGE 2
#define SAP_ALL 3
#define FMNAMESZ 8
#define MAXAPUSH 8
#define GVID_SETTABLE ((('G' << 8) | 'v') << 16 | 1)

typedef unsigned int major_t;

typedef struct gvid {
    unsigned long gvid_num;
    dev_t *gvid_buf;
    major_t gvid_maj;
} gvid_t;

struct apcommon {
    unsigned int apc_cmd;
    long apc_major;
    long apc_minor;
    long apc_lastminor;
    unsigned int apc_npush;
};

struct strapush {
    struct apcommon sap_common;
    char sap_list[MAXAPUSH][FMNAMESZ + 1];
};

#define sap_cmd sap_common.apc_cmd
#define sap_major sap_common.apc_major
#define sap_minor sap_common.apc_minor
#define sap_lastminor sap_common.apc_lastminor
#define sap_npush sap_common.apc_npush

static int workstation_initialized;

static int open_console(void) {
    int fd;

    fd = open("/dev/vt00", O_RDWR);
    if(fd >= 0)
        return fd;
    fd = open("/dev/syscon", O_RDWR);
    if(fd < 0)
        fd = open("/dev/console", O_RDWR);
    if(fd < 0)
        fd = open("/dev/null", O_RDWR);
    return fd;
}

static void configure_autopush_entry(long major, long minor, long lastminor,
        unsigned int command, const char *const modules[], unsigned int count) {
    struct strapush push = {0};
    int fd;
    unsigned int i;

    fd = open("/dev/sad/admin", O_RDWR);
    if(fd < 0)
        return;

    push.sap_cmd = command;
    push.sap_major = major;
    push.sap_minor = minor;
    push.sap_lastminor = lastminor;
    push.sap_npush = count;

    for(i = 0; i < count && i < MAXAPUSH; ++i) {
        snprintf(push.sap_list[i], sizeof(push.sap_list[i]), "%s", modules[i]);
    }

    ioctl(fd, SAD_SAP, &push);
    close(fd);
}

static void configure_console_autopush(void) {
    static const char *const console_modules[] = {
        "char",
        "ansi",
        "ldterm",
        "ttcompat"
    };
    static const char *const tty_modules[] = {
        "ldterm",
        "ttcompat"
    };

    configure_autopush_entry(5, -1, 0, SAP_ALL,
        console_modules, sizeof(console_modules) / sizeof(console_modules[0]));
    configure_autopush_entry(3, 0, 129, SAP_RANGE,
        tty_modules, sizeof(tty_modules) / sizeof(tty_modules[0]));
}

static void initialize_workstation_console(void) {
    struct stat kdvm_stat;
    struct stat mux_stat;
    gvid_t mapping;
    dev_t video_devices[1];
    int muxfd;
    int devfd;
    int gvidfd;

    if(workstation_initialized)
        return;

    muxfd = open("/dev/vt00", O_RDWR);
    if(muxfd < 0)
        return;

    if(fstat(muxfd, &mux_stat) < 0) {
        close(muxfd);
        return;
    }

    devfd = open("/dev/kd/kd00", O_RDWR);
    if(devfd < 0) {
        close(muxfd);
        return;
    }

    if(ioctl(muxfd, I_PLINK, devfd) < 0) {
        close(devfd);
        close(muxfd);
        return;
    }

    if(stat("/dev/kd/kdvm00", &kdvm_stat) == 0) {
        video_devices[0] = kdvm_stat.st_rdev;
        gvidfd = open("/dev/vidadm", O_RDWR);
        if(gvidfd >= 0) {
            mapping.gvid_num = 1;
            mapping.gvid_buf = video_devices;
            mapping.gvid_maj = (major_t)getmajor(mux_stat.st_rdev);
            ioctl(gvidfd, GVID_SETTABLE, &mapping);
            close(gvidfd);
        }
    }

    close(devfd);
    close(muxfd);
    workstation_initialized = 1;
}

static void configure_console(int fd) {
    struct termios modes;

    if(fd < 0 || !isatty(fd))
        return;
    if(tcgetattr(fd, &modes) < 0)
        return;

    modes.c_iflag &= ~(IGNCR | INLCR);
    modes.c_iflag |= BRKINT | IGNPAR | ISTRIP | IXON | IXANY | ICRNL;
    modes.c_oflag |= OPOST | ONLCR | XTABS;
    modes.c_cflag &= ~CSIZE;
    modes.c_cflag |= CS8 | CREAD;
    modes.c_lflag |= ISIG | ICANON | ECHO | ECHOK;
    modes.c_cc[VINTR] = 0x7f;
    modes.c_cc[VQUIT] = 0x1c;
    modes.c_cc[VERASE] = '\b';
    modes.c_cc[VKILL] = 0x15;
    modes.c_cc[VEOF] = 0x04;
    tcsetattr(fd, TCSANOW, &modes);
}

static void init_stdio(void) {
    int fd;

    fd = open_console();
    if(fd < 0)
        return;

    configure_console(fd);

    if(fd != STDIN_FILENO) {
        dup2(fd, STDIN_FILENO);
    }
    if(fd != STDOUT_FILENO) {
        dup2(fd, STDOUT_FILENO);
    }
    if(fd != STDERR_FILENO) {
        dup2(fd, STDERR_FILENO);
    }
    if(fd != STDIN_FILENO && fd != STDOUT_FILENO && fd != STDERR_FILENO) {
        close(fd);
    }
}

char* const default_environ[] = {
    "PATH=/bin:/usr/bin:/sbin:/usr/sbin",
    "HOME=/root",
    "TERM=vt100",
    nullptr
};

int launch_process(const char *path, char *const argv[], char *const envp[]) {
    if(fork() == 0) {
        if(setsid() >= 0) {
            init_stdio();
        }
        execve(path, argv, envp);
        _exit(1);
    }
    return 0;
}

int main(int argc, char **argv) {
    static char *const shell_argv[] = {
        (char *)"-bash",
        nullptr
    };

    configure_console_autopush();
    initialize_workstation_console();
    init_stdio();
    printf("The system is coming up.\r\n");
    fflush(stdout);

    launch_process("/bin/bash", shell_argv, default_environ);

    for(;;) {
        pause();
    }
}