#ifndef HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_SIGNAL_H
#define HOST_TOOLS_ORIGINAL_UFS_FSCK_COMPAT_SYS_SIGNAL_H

typedef void (*sig_handler_t)(int);

#define SIGQUIT 3
#define SIGINT 2
#define SIG_DFL ((sig_handler_t)0)
#define SIG_IGN ((sig_handler_t)1)

extern sig_handler_t signal(int signum, sig_handler_t handler);

#endif