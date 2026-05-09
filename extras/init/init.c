#include <fcntl.h>
#include <stdio.h>
#include <stropts.h>
#include <sys/ioctl.h>
#include <unistd.h>

static void push_stream_module(int fd, const char *name) {
    if(fd >= 0)
        ioctl(fd, I_PUSH, name);
}

static void setup_console_stream(int fd) {
    push_stream_module(fd, "ansi");
    push_stream_module(fd, "ldterm");
}

static void init_stdio(void) {
    int fd;

    fd = open("/dev/console", O_RDWR);
    if(fd < 0)
        fd = open("/dev/null", O_RDWR);
    if(fd < 0)
        return;

    setup_console_stream(fd);

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

int main(int argc, char **argv) {
    init_stdio();
    printf("The system is coming up.\r\n");
    fflush(stdout);
    return 0;
}