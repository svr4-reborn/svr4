#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

typedef unsigned char unchar;
typedef unsigned short ushort;
typedef unsigned int major_t;

#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))

#define VTIOC ('v' << 8)
#define VT_OPENQRY (VTIOC | 1)
#define VT_GETSTATE (VTIOC | 100)

#define GIO_ATTR ('a' << 8)
#define KBIO_GETMODE (('k' << 8) | 14)

#define KIOC ('K' << 8)
#define KDDISPTYPE (KIOC | 1)
#define KDMAPDISP (KIOC | 2)
#define KDUNMAPDISP (KIOC | 3)
#define KDMKTONE (KIOC | 8)
#define KDGETMODE (KIOC | 9)
#define KDSETMODE (KIOC | 10)
#define KDADDIO (KIOC | 11)
#define KDDELIO (KIOC | 12)
#define KDSBORDER (KIOC | 13)
#define KDQUEMODE (KIOC | 15)
#define KDDISPINFO (KIOC | 18)
#define KDGKBSTATE (KIOC | 19)
#define KDENABIO (KIOC | 60)
#define KDDISABIO (KIOC | 61)
#define KIOCSOUND (KIOC | 63)
#define KDGKBTYPE (KIOC | 64)
#define KDGETLED (KIOC | 65)
#define KDSETLED (KIOC | 66)

#define WSIOC (('w' << 24) | ('s' << 16))
#define KDVDCTYPE (WSIOC | 1)

#define MODESWITCH ('x' << 8)
#define MAPADAPTER ('m' << 8)

#define MAPCONS (MAPADAPTER)
#define MAPMONO (MAPADAPTER | 1)
#define MAPCGA (MAPADAPTER | 2)
#define MAPEGA (MAPADAPTER | 4)
#define MAPVGA (MAPADAPTER | 5)

#define CONSIOC ('c' << 8)
#define CONS_CURRENT (CONSIOC | 1)
#define CONS_GET (CONSIOC | 2)
#define CONS_GETINFO (CONSIOC | 73)

#define GVIOC ('G' << 8 | 'v')
#define GVID_SETTABLE ((GVIOC << 16) | 1)
#define GVID_GETTABLE ((GVIOC << 16) | 2)

#define KD_MONO 1
#define KD_HERCULES 2
#define KD_CGA 3
#define KD_EGA 4
#define KD_VGA 5
#define KD_VDC400 6
#define KD_VDC750 7
#define KD_VDC600 8

#define KD_UNKNOWN 0
#define KD_STAND_M 1
#define KD_STAND_C 2
#define KD_MULTI_M 3
#define KD_MULTI_C 4

#define KD_TEXT0 0
#define KD_GRAPHICS 1
#define KD_TEXT1 2

#define KBM_XT 0

#define LED_SCR 0x01
#define LED_NUM 0x02
#define LED_CAP 0x04

#define DM_B40x25 0
#define DM_C40x25 1
#define DM_B80x25 2
#define DM_C80x25 3
#define DM_BG320 4
#define DM_CG320 5
#define DM_BG640 6
#define DM_EGAMONO80x25 7
#define DM_ENH_B80x43 10
#define DM_ENH_C80x43 11
#define DM_CG320_D 13
#define DM_CG640_E 14
#define DM_EGAMONOAPA 15
#define DM_CG640x350 16
#define DM_ENHMONOAPA2 17
#define DM_ENH_CG640 18
#define DM_ENH_B40x25 19
#define DM_ENH_C40x25 20
#define DM_ENH_B80x25 21
#define DM_ENH_C80x25 22
#define DM_VGA_C40x25 23
#define DM_VGA_C80x25 24
#define DM_VGAMONO80x25 25
#define DM_VGA640x480C 26
#define DM_VGA640x480E 27
#define DM_VGA320x200 28
#define DM_VGA_B40x25 29
#define DM_VGA_B80x25 30
#define DM_VGAMONOAPA 31
#define DM_VGA_CG640 32
#define DM_ENH_CGA 33
#define DM_ATT_640 34
#define DM_VGA_B132x25 35
#define DM_VGA_C132x25 36
#define DM_VGA_B132x43 37
#define DM_VGA_C132x43 38
#define DM_VDC800x600E 39
#define DM_VDC640x400V 40

#define M_ENH_B80x43 0x70
#define M_ENH_C80x43 0x71
#define M_MCA_MODE 0xff

#define SW_CG320 (MODESWITCH | DM_CG320)
#define SW_CG640x350 (MODESWITCH | DM_CG640x350)
#define SW_ATT640 (MODESWITCH | DM_ATT_640)
#define SW_VGA640x480C (MODESWITCH | DM_VGA640x480C)
#define SW_VGA640x480E (MODESWITCH | DM_VGA640x480E)
#define SW_VGA320x200 (MODESWITCH | DM_VGA320x200)
#define SW_VDC800x600E (MODESWITCH | DM_VDC800x600E)
#define SW_VDC640x400V (MODESWITCH | DM_VDC640x400V)

#define XQ_BUTTON 0
#define XQ_MOTION 1
#define XQ_KEY 2

struct vt_stat {
	ushort v_active;
	ushort v_signal;
	ushort v_state;
};

struct colors {
	char fore;
	char back;
};

struct vid_info {
	short size;
	short m_num;
	ushort mv_row;
	ushort mv_col;
	ushort mv_rsz;
	ushort mv_csz;
	struct colors mv_norm;
	struct colors mv_rev;
	struct colors mv_grfc;
	unsigned char mv_ovscan;
	unsigned char mk_keylock;
};

struct kd_disparam {
	long type;
	char *addr;
	ushort ioaddr[64];
};

struct kd_vdctype {
	long cntlr;
	long dsply;
	long rsrvd;
};

struct kd_dispinfo {
	char *vaddr;
	unsigned long physaddr;
	unsigned long size;
};

struct kd_memloc {
	char *vaddr;
	char *physaddr;
	long length;
	long ioflg;
};

struct kd_quemode {
	int qsize;
	int signo;
	char *qaddr;
};

struct xqEvent {
	unchar xq_type;
	unchar xq_code;
	char xq_x;
	char xq_y;
	time_t xq_time;
};

struct xqEventQueue {
	char xq_sigenable;
	int xq_head;
	int xq_tail;
	time_t xq_curtime;
	int xq_size;
	struct xqEvent xq_events[1];
};

typedef struct gvid {
	unsigned long gvid_num;
	dev_t *gvid_buf;
	major_t gvid_maj;
} gvid_t;

struct named_value {
	int value;
	const char *name;
};

enum draw_kind {
	DRAW_RAW,
	DRAW_LINEAR8,
};

struct graphics_mode {
	const char *name;
	int switch_ioctl;
	int map_ioctl;
	int width;
	int height;
	enum draw_kind draw_kind;
};

struct options {
	int run_video;
	int run_admin;
	int run_queue;
	int run_graphics;
	int choose_default_graphics;
	int timeout_seconds;
	int hold_seconds;
	int queue_seconds;
	const struct graphics_mode *graphics_mode;
};

struct device_handles {
	int vt_fd;
	int stream_fd;
	int kdvm_fd;
	int video_fd;
	int vidadm_fd;
	const char *vt_path;
	const char *stream_path;
	const char *kdvm_path;
	const char *video_path;
	const char *vidadm_path;
};

static int dup_first_tty(const int *fds, size_t count, const char **opened_path)
{
	size_t index;
	int duplicate;
	static const char *const fd_names[] = {"<stdin>", "<stdout>", "<stderr>"};

	for (index = 0; index < count; ++index) {
		if (fds[index] < 0 || !isatty(fds[index]))
			continue;
		duplicate = dup(fds[index]);
		if (duplicate >= 0) {
			if (opened_path)
				*opened_path = fd_names[index];
			return duplicate;
		}
	}

	if (opened_path)
		*opened_path = NULL;
	return -1;
}

static const struct named_value display_types[] = {
	{KD_MONO, "mono"},
	{KD_HERCULES, "hercules"},
	{KD_CGA, "cga"},
	{KD_EGA, "ega"},
	{KD_VGA, "vga"},
	{KD_VDC400, "vdc400"},
	{KD_VDC750, "vdc750"},
	{KD_VDC600, "vdc600"},
};

static const struct named_value monitor_types[] = {
	{KD_UNKNOWN, "unknown"},
	{KD_STAND_M, "standard-mono"},
	{KD_STAND_C, "standard-color"},
	{KD_MULTI_M, "multi-mono"},
	{KD_MULTI_C, "multi-color"},
};

static const struct named_value console_modes[] = {
	{DM_B40x25, "b40x25"},
	{DM_C40x25, "c40x25"},
	{DM_B80x25, "b80x25"},
	{DM_C80x25, "c80x25"},
	{DM_BG320, "bg320"},
	{DM_CG320, "cg320"},
	{DM_BG640, "bg640"},
	{DM_EGAMONO80x25, "egamono80x25"},
	{DM_ENH_B80x43, "enh-b80x43"},
	{DM_ENH_C80x43, "enh-c80x43"},
	{DM_CG320_D, "cg320-d"},
	{DM_CG640_E, "cg640-e"},
	{DM_EGAMONOAPA, "egamonoapa"},
	{DM_CG640x350, "cg640x350"},
	{DM_ENHMONOAPA2, "enhmonoapa2"},
	{DM_ENH_CG640, "enh-cg640"},
	{DM_ENH_B40x25, "enh-b40x25"},
	{DM_ENH_C40x25, "enh-c40x25"},
	{DM_ENH_B80x25, "enh-b80x25"},
	{DM_ENH_C80x25, "enh-c80x25"},
	{DM_VGA_C40x25, "vga-c40x25"},
	{DM_VGA_C80x25, "vga-c80x25"},
	{DM_VGAMONO80x25, "vga-mono80x25"},
	{DM_VGA640x480C, "vga640x480c"},
	{DM_VGA640x480E, "vga640x480e"},
	{DM_VGA320x200, "vga320x200"},
	{DM_VGA_B40x25, "vga-b40x25"},
	{DM_VGA_B80x25, "vga-b80x25"},
	{DM_VGAMONOAPA, "vga-monoapa"},
	{DM_VGA_CG640, "vga-cg640"},
	{DM_ATT_640, "att640"},
	{DM_VGA_B132x25, "vga-b132x25"},
	{DM_VGA_C132x25, "vga-c132x25"},
	{DM_VGA_B132x43, "vga-b132x43"},
	{DM_VGA_C132x43, "vga-c132x43"},
	{DM_VDC800x600E, "vdc800x600e"},
	{DM_VDC640x400V, "vdc640x400v"},
	{M_ENH_B80x43, "xenix-enh-b80x43"},
	{M_ENH_C80x43, "xenix-enh-c80x43"},
	{M_MCA_MODE, "mca-mode"},
};

static const struct graphics_mode graphics_modes[] = {
	{"cg320", SW_CG320, MAPCGA, 320, 200, DRAW_RAW},
	{"cg640x350", SW_CG640x350, MAPEGA, 640, 350, DRAW_RAW},
	{"att640", SW_ATT640, MAPCONS, 640, 400, DRAW_RAW},
	{"vga320x200", SW_VGA320x200, MAPVGA, 320, 200, DRAW_LINEAR8},
	{"vga640x480c", SW_VGA640x480C, MAPVGA, 640, 480, DRAW_RAW},
	{"vga640x480e", SW_VGA640x480E, MAPVGA, 640, 480, DRAW_RAW},
	{"vdc640x400v", SW_VDC640x400V, MAPCONS, 640, 400, DRAW_LINEAR8},
	{"vdc800x600e", SW_VDC800x600E, MAPCONS, 800, 600, DRAW_RAW},
};

static void print_usage(const char *program)
{
	printf("usage: %s [--all] [--queue] [--graphics MODE] [--timeout SEC] [--hold SEC] [--queue-seconds SEC]\n", program);
	printf("       %s [--no-video] [--no-admin] [--list-modes]\n", program);
}

static const char *lookup_name(const struct named_value *table, size_t table_size, int value)
{
	size_t index;

	for (index = 0; index < table_size; ++index) {
		if (table[index].value == value)
			return table[index].name;
	}

	return "unknown";
}

static const char *event_type_name(int value)
{
	switch (value) {
	case XQ_BUTTON:
		return "button";
	case XQ_MOTION:
		return "motion";
	case XQ_KEY:
		return "key";
	default:
		return "unknown";
	}
}

static const struct graphics_mode *find_graphics_mode(const char *name)
{
	size_t index;

	for (index = 0; index < ARRAY_SIZE(graphics_modes); ++index) {
		if (!strcmp(graphics_modes[index].name, name))
			return &graphics_modes[index];
	}

	return NULL;
}

static void list_graphics_modes(void)
{
	size_t index;

	for (index = 0; index < ARRAY_SIZE(graphics_modes); ++index) {
		printf("%s\n", graphics_modes[index].name);
	}
}

static int parse_positive_int(const char *text, int *value)
{
	char *end;
	long parsed;

	errno = 0;
	parsed = strtol(text, &end, 10);
	if (errno || !end || *end || parsed <= 0 || parsed > 3600)
		return -1;

	*value = (int)parsed;
	return 0;
}

static int parse_options(int argc, char **argv, struct options *options)
{
	int index;

	memset(options, 0, sizeof(*options));
	options->run_video = 1;
	options->run_admin = 1;
	options->timeout_seconds = 10;
	options->hold_seconds = 2;
	options->queue_seconds = 5;

	for (index = 1; index < argc; ++index) {
		if (!strcmp(argv[index], "--help")) {
			print_usage(argv[0]);
			return 1;
		}
		if (!strcmp(argv[index], "--list-modes")) {
			list_graphics_modes();
			return 1;
		}
		if (!strcmp(argv[index], "--all")) {
			options->run_queue = 1;
			options->run_graphics = 1;
			options->choose_default_graphics = 1;
			continue;
		}
		if (!strcmp(argv[index], "--queue")) {
			options->run_queue = 1;
			continue;
		}
		if (!strcmp(argv[index], "--no-video")) {
			options->run_video = 0;
			continue;
		}
		if (!strcmp(argv[index], "--no-admin")) {
			options->run_admin = 0;
			continue;
		}
		if (!strcmp(argv[index], "--graphics")) {
			if (index + 1 >= argc) {
				fprintf(stderr, "--graphics requires a mode name\n");
				return -1;
			}
			options->graphics_mode = find_graphics_mode(argv[++index]);
			if (!options->graphics_mode) {
				fprintf(stderr, "unknown graphics mode: %s\n", argv[index]);
				return -1;
			}
			options->run_graphics = 1;
			options->choose_default_graphics = 0;
			continue;
		}
		if (!strncmp(argv[index], "--graphics=", 11)) {
			options->graphics_mode = find_graphics_mode(argv[index] + 11);
			if (!options->graphics_mode) {
				fprintf(stderr, "unknown graphics mode: %s\n", argv[index] + 11);
				return -1;
			}
			options->run_graphics = 1;
			options->choose_default_graphics = 0;
			continue;
		}
		if (!strcmp(argv[index], "--timeout")) {
			if (index + 1 >= argc || parse_positive_int(argv[++index], &options->timeout_seconds)) {
				fprintf(stderr, "invalid --timeout value\n");
				return -1;
			}
			continue;
		}
		if (!strcmp(argv[index], "--hold")) {
			if (index + 1 >= argc || parse_positive_int(argv[++index], &options->hold_seconds)) {
				fprintf(stderr, "invalid --hold value\n");
				return -1;
			}
			continue;
		}
		if (!strcmp(argv[index], "--queue-seconds")) {
			if (index + 1 >= argc || parse_positive_int(argv[++index], &options->queue_seconds)) {
				fprintf(stderr, "invalid --queue-seconds value\n");
				return -1;
			}
			continue;
		}

		fprintf(stderr, "unknown option: %s\n", argv[index]);
		return -1;
	}

	return 0;
}

static void report_pass(const char *scope, const char *detail)
{
	printf("[PASS] %s %s\n", scope, detail);
}

static void report_skip(const char *scope, const char *detail)
{
	printf("[SKIP] %s %s\n", scope, detail);
}

static void report_fail(const char *scope, const char *detail)
{
	printf("[FAIL] %s %s: %s\n", scope, detail, strerror(errno));
}

static int open_first_rw(const char *const *paths, size_t count, const char **opened_path)
{
	size_t index;
	int fd;

	for (index = 0; index < count; ++index) {
		fd = open(paths[index], O_RDWR);
		if (fd >= 0) {
			if (opened_path)
				*opened_path = paths[index];
			return fd;
		}
	}

	if (opened_path)
		*opened_path = NULL;
	return -1;
}

static void close_if_open(int *fd)
{
	if (*fd >= 0) {
		close(*fd);
		*fd = -1;
	}
}

static int open_devices(struct device_handles *devices)
{
	static const int stdio_fds[] = {STDIN_FILENO, STDOUT_FILENO, STDERR_FILENO};
	static const char *const vt_paths[] = {"/dev/vt00", "/dev/syscon", "/dev/console", "/dev/tty"};
	static const char *const stream_paths[] = {"/dev/tty", "/dev/kd/kd00", "/dev/vt00", "/dev/syscon", "/dev/console"};
	static const char *const kdvm_paths[] = {"/dev/kd/kdvm00"};
	static const char *const video_paths[] = {"/dev/video"};
	static const char *const vidadm_paths[] = {"/dev/vidadm"};

	memset(devices, 0, sizeof(*devices));
	devices->vt_fd = -1;
	devices->stream_fd = -1;
	devices->kdvm_fd = -1;
	devices->video_fd = -1;
	devices->vidadm_fd = -1;

	devices->vt_fd = open_first_rw(vt_paths, ARRAY_SIZE(vt_paths), &devices->vt_path);
	if (devices->vt_fd < 0)
		return -1;

	devices->stream_fd = dup_first_tty(stdio_fds, ARRAY_SIZE(stdio_fds), &devices->stream_path);
	if (devices->stream_fd < 0)
		devices->stream_fd = open_first_rw(stream_paths, ARRAY_SIZE(stream_paths), &devices->stream_path);
	if (devices->stream_fd < 0)
		return -1;

	devices->kdvm_fd = open_first_rw(kdvm_paths, ARRAY_SIZE(kdvm_paths), &devices->kdvm_path);
	if (devices->kdvm_fd < 0)
		return -1;

	devices->video_fd = open_first_rw(video_paths, ARRAY_SIZE(video_paths), &devices->video_path);
	devices->vidadm_fd = open_first_rw(vidadm_paths, ARRAY_SIZE(vidadm_paths), &devices->vidadm_path);
	return 0;
}

static void close_devices(struct device_handles *devices)
{
	close_if_open(&devices->vt_fd);
	close_if_open(&devices->stream_fd);
	close_if_open(&devices->kdvm_fd);
	close_if_open(&devices->video_fd);
	close_if_open(&devices->vidadm_fd);
}

static ushort pick_probe_port(const struct kd_disparam *disparam)
{
	size_t index;

	for (index = 0; index < ARRAY_SIZE(disparam->ioaddr); ++index) {
		if (disparam->ioaddr[index])
			return disparam->ioaddr[index];
	}

	return 0;
}

static int fetch_console_mode_value(int fd, int *mode_value)
{
	int rc;

	errno = 0;
	rc = ioctl(fd, CONS_GET, 0);
	if (rc < 0)
		return -1;

	*mode_value = rc;
	return 0;
}

static int fetch_console_adapter_value(int fd, int *adapter_value)
{
	int rc;

	errno = 0;
	rc = ioctl(fd, CONS_CURRENT, 0);
	if (rc < 0)
		return -1;

	*adapter_value = rc;
	return 0;
}

static int fetch_text_graphics_mode(int fd, int *mode)
{
	if (ioctl(fd, KDGETMODE, mode) < 0)
		return -1;

	return 0;
}

static int restore_display_mode(int fd, int console_mode_value, int text_graphics_mode)
{
	if (ioctl(fd, MODESWITCH | (console_mode_value & 0xff), 0) < 0)
		return -1;

	if (ioctl(fd, KDSETMODE, text_graphics_mode) < 0)
		return -1;

	return 0;
}

static unsigned long sample_checksum(volatile unsigned char *buffer, size_t size)
{
	unsigned long checksum;
	size_t limit;
	size_t index;

	checksum = 0;
	limit = size < 256 ? size : 256;
	for (index = 0; index < limit; ++index)
		checksum = (checksum * 33UL) ^ buffer[index];

	return checksum;
}

static size_t round_up_page_size(size_t size)
{
	long page_size;
	size_t page;

	page_size = sysconf(_SC_PAGESIZE);
	page = page_size > 0 ? (size_t)page_size : 4096U;
	return (size + page - 1) & ~(page - 1);
}

static void *reserve_mapping_address(size_t size)
{
	void *address;

	address = mmap(NULL, size, PROT_READ | PROT_WRITE,
		MAP_PRIVATE
#ifdef MAP_ANONYMOUS
		| MAP_ANONYMOUS
#elif defined(MAP_ANON)
		| MAP_ANON
#endif
		, -1, 0);
	if (address == MAP_FAILED)
		return NULL;

	if (munmap(address, size) < 0)
		return NULL;

	return address;
}

static void draw_raw_pattern(volatile unsigned char *framebuffer, size_t size)
{
	size_t index;

	for (index = 0; index < size; ++index)
		framebuffer[index] = (unsigned char)(((index / 64U) ^ (index / 7U)) & 0xffU);
}

static void draw_linear8_pattern(volatile unsigned char *framebuffer, size_t size, int width, int height)
{
	size_t stride;
	size_t line_x;
	int x;
	int y;

	if (width <= 0 || height <= 0) {
		draw_raw_pattern(framebuffer, size);
		return;
	}

	stride = (size_t)width;
	if ((size_t)height > 0 && stride * (size_t)height > size) {
		stride = size / (size_t)height;
		if (!stride) {
			draw_raw_pattern(framebuffer, size);
			return;
		}
	}

	for (y = 0; y < height; ++y) {
		for (x = 0; x < width && (size_t)x < stride; ++x) {
			framebuffer[(size_t)y * stride + (size_t)x] = (unsigned char)(((x / 4) + (y / 2)) & 0xff);
		}
	}

	for (x = 0; x < width && (size_t)x < stride; ++x) {
		framebuffer[(size_t)(height / 2) * stride + (size_t)x] = 0xff;
	}

	line_x = (size_t)(width / 2);
	if (line_x < stride) {
		for (y = 0; y < height; ++y)
			framebuffer[(size_t)y * stride + line_x] = 0xff;
	}
}

static int exercise_kdmapdisp_once(int fd, const struct kd_dispinfo *dispinfo)
{
	struct kd_memloc memloc;
	void *mapping_address;
	unsigned long checksum;
	size_t rounded_size;

	if (!dispinfo->size) {
		report_skip("graphics", "KDMAPDISP skipped because display size is zero");
		return 0;
	}

	rounded_size = round_up_page_size((size_t)dispinfo->size);
	mapping_address = reserve_mapping_address(rounded_size);
	if (!mapping_address) {
		report_skip("graphics", "KDMAPDISP skipped because no free user mapping hole could be reserved");
		return 0;
	}

	memset(&memloc, 0, sizeof(memloc));
	memloc.vaddr = (char *)mapping_address;
	memloc.physaddr = (char *)(uintptr_t)dispinfo->physaddr;
	memloc.length = (long)dispinfo->size;
	memloc.ioflg = 1;

	if (ioctl(fd, KDMAPDISP, &memloc) < 0) {
		report_fail("graphics", "KDMAPDISP");
		return -1;
	}

	checksum = sample_checksum((volatile unsigned char *)memloc.vaddr, (size_t)dispinfo->size);
	printf("[PASS] graphics KDMAPDISP checksum=0x%08lx vaddr=%p phys=0x%08lx size=%lu\n",
		checksum, memloc.vaddr, dispinfo->physaddr, dispinfo->size);

	if (ioctl(fd, KDUNMAPDISP, 0) < 0) {
		report_fail("graphics", "KDUNMAPDISP after KDMAPDISP");
		return -1;
	}

	report_pass("graphics", "KDUNMAPDISP after KDMAPDISP");
	return 0;
}

static int exercise_mapped_draw(int fd, const struct graphics_mode *mode, const struct kd_dispinfo *dispinfo)
{
	int rc;
	volatile unsigned char *framebuffer;

	errno = 0;
	rc = ioctl(fd, mode->map_ioctl, 0);
	if (rc < 0) {
		report_fail("graphics", "xenix map ioctl");
		return -1;
	}

	framebuffer = (volatile unsigned char *)(uintptr_t)(unsigned int)rc;
	if (mode->draw_kind == DRAW_LINEAR8)
		draw_linear8_pattern(framebuffer, (size_t)dispinfo->size, mode->width, mode->height);
	else
		draw_raw_pattern(framebuffer, (size_t)dispinfo->size);

	printf("[PASS] graphics drew test pattern for %s at %p size=%lu\n",
		mode->name, (void *)framebuffer, dispinfo->size);

	if (ioctl(fd, KDUNMAPDISP, 0) < 0) {
		report_fail("graphics", "KDUNMAPDISP after xenix map");
		return -1;
	}

	report_pass("graphics", "KDUNMAPDISP after xenix map");
	return 0;
}

static int graphics_worker(int fd, const struct graphics_mode *mode, int original_console_mode, int original_text_graphics_mode, int hold_seconds)
{
	struct kd_dispinfo dispinfo;
	int status;

	if (ioctl(fd, mode->switch_ioctl, 0) < 0) {
		report_fail("graphics", "mode switch");
		return 2;
	}

	printf("[PASS] graphics switched into %s\n", mode->name);

	if (ioctl(fd, KDSETMODE, KD_GRAPHICS) < 0) {
		report_fail("graphics", "KDSETMODE KD_GRAPHICS");
		return 1;
	}

	report_pass("graphics", "KDSETMODE KD_GRAPHICS");

	if (ioctl(fd, KDDISPINFO, &dispinfo) < 0) {
		report_fail("graphics", "KDDISPINFO in graphics mode");
		return 1;
	}

	printf("[PASS] graphics KDDISPINFO phys=0x%08lx size=%lu\n", dispinfo.physaddr, dispinfo.size);

	status = exercise_kdmapdisp_once(fd, &dispinfo);
	if (status)
		return 1;

	status = exercise_mapped_draw(fd, mode, &dispinfo);
	if (status)
		return 1;

	sleep((unsigned int)hold_seconds);

	if (restore_display_mode(fd, original_console_mode, original_text_graphics_mode) < 0) {
		report_fail("graphics", "restore original display mode in worker");
		return 1;
	}

	report_pass("graphics", "restored original display mode in worker");
	return 0;
}

static int run_graphics_mode_test(int fd, const struct graphics_mode *mode, int timeout_seconds, int hold_seconds)
{
	int original_console_mode;
	int original_text_graphics_mode;
	pid_t child;
	int status;
	time_t deadline;
	pid_t wait_result;
	int child_status;

	if (fetch_console_mode_value(fd, &original_console_mode) < 0) {
		report_fail("graphics", "CONS_GET before mode test");
		return 1;
	}

	if (fetch_text_graphics_mode(fd, &original_text_graphics_mode) < 0) {
		report_fail("graphics", "KDGETMODE before mode test");
		return 1;
	}

	child = fork();
	if (child < 0) {
		report_fail("graphics", "fork watchdog worker");
		return 1;
	}

	if (!child) {
		status = graphics_worker(fd, mode, original_console_mode, original_text_graphics_mode, hold_seconds);
		fflush(stdout);
		fflush(stderr);
		exit(status);
	}

	deadline = time(NULL) + timeout_seconds;
	child_status = 1;
	for (;;) {
		wait_result = waitpid(child, &status, WNOHANG);
		if (wait_result == child) {
			if (WIFEXITED(status))
				child_status = WEXITSTATUS(status);
			break;
		}
		if (wait_result < 0) {
			report_fail("graphics", "waitpid");
			break;
		}
		if (time(NULL) >= deadline) {
			kill(child, SIGKILL);
			waitpid(child, &status, 0);
			printf("[FAIL] graphics mode %s timed out after %d seconds\n", mode->name, timeout_seconds);
			child_status = 1;
			break;
		}
		sleep(1);
	}

	if (restore_display_mode(fd, original_console_mode, original_text_graphics_mode) < 0)
		report_fail("graphics", "parent restore after worker exit");
	else
		report_pass("graphics", "parent restore after worker exit");

	return child_status;
}

static int run_console_queries(int vt_fd, int stream_fd)
{
	struct vt_stat vt_state;
	struct vid_info vid_info;
	unsigned char keyboard_type;
	unsigned char leds;
	ushort keyboard_state;
	int ioctl_result;
	int kb_mode;
	int attribute;
	int free_vt;
	int failures;
	char detail[160];

	failures = 0;

	if (ioctl(vt_fd, VT_GETSTATE, &vt_state) < 0) {
		report_fail("console", "VT_GETSTATE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "VT_GETSTATE active=%u signal=%u state=0x%x",
			vt_state.v_active, vt_state.v_signal, vt_state.v_state);
		report_pass("console", detail);
	}

	free_vt = -1;
	if (ioctl(vt_fd, VT_OPENQRY, &free_vt) < 0) {
		report_fail("console", "VT_OPENQRY");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "VT_OPENQRY free-vt=%d", free_vt);
		report_pass("console", detail);
	}

	if (ioctl(vt_fd, CONS_GETINFO, &vid_info) < 0) {
		report_fail("console", "CONS_GETINFO");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "CONS_GETINFO rows=%u cols=%u cursor=(%u,%u) overscan=%u",
			vid_info.mv_rsz, vid_info.mv_csz, vid_info.mv_row, vid_info.mv_col, vid_info.mv_ovscan);
		report_pass("console", detail);
	}

	if (ioctl(stream_fd, KDGKBTYPE, &keyboard_type) < 0) {
		report_fail("console", "KDGKBTYPE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDGKBTYPE keyboard=%u", keyboard_type);
		report_pass("console", detail);
	}

	ioctl_result = ioctl(stream_fd, KBIO_GETMODE, 0);
	if (ioctl_result < 0) {
		report_fail("console", "KBIO_GETMODE");
		++failures;
	} else {
		kb_mode = ioctl_result;
		snprintf(detail, sizeof(detail), "KBIO_GETMODE mode=%s", kb_mode == KBM_XT ? "xt" : "unknown");
		report_pass("console", detail);
	}

	errno = 0;
	attribute = ioctl(stream_fd, GIO_ATTR, 0);
	if (attribute < 0) {
		report_fail("console", "GIO_ATTR");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "GIO_ATTR attr=0x%x", attribute);
		report_pass("console", detail);
	}

	if (ioctl(stream_fd, KDGETLED, &leds) < 0) {
		report_fail("console", "KDGETLED");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDGETLED leds=0x%x", leds);
		report_pass("console", detail);
		if (ioctl(stream_fd, KDSETLED, (unsigned int)(leds ^ LED_SCR)) < 0) {
			report_fail("console", "KDSETLED toggle scroll lock");
			++failures;
		} else {
			usleep(100000);
			if (ioctl(stream_fd, KDSETLED, (unsigned int)leds) < 0) {
				report_fail("console", "KDSETLED restore");
				++failures;
			} else {
				report_pass("console", "KDSETLED toggled and restored");
			}
		}
	}

	if (ioctl(stream_fd, KDGKBSTATE, &keyboard_state) < 0) {
		report_skip("console", "KDGKBSTATE unsupported or unavailable");
	} else {
		snprintf(detail, sizeof(detail), "KDGKBSTATE state=0x%x", keyboard_state);
		report_pass("console", detail);
	}

	return failures;
}

static int run_kdvm_queries(int kdvm_fd, struct kd_disparam *disparam_out, int *adapter_type_out)
{
	struct kd_disparam disparam;
	struct kd_vdctype vdctype;
	struct kd_dispinfo dispinfo;
	int console_adapter;
	int console_mode;
	int text_graphics_mode;
	ushort probe_port;
	int failures;
	char detail[224];

	failures = 0;
	memset(&disparam, 0, sizeof(disparam));

	if (ioctl(kdvm_fd, KDDISPTYPE, &disparam) < 0) {
		report_fail("kdvm", "KDDISPTYPE");
		++failures;
	} else {
		probe_port = pick_probe_port(&disparam);
		snprintf(detail, sizeof(detail), "KDDISPTYPE type=%s addr=%p first-io=0x%x",
			lookup_name(display_types, ARRAY_SIZE(display_types), (int)disparam.type),
			disparam.addr, probe_port);
		report_pass("kdvm", detail);
		if (disparam_out)
			*disparam_out = disparam;
	}

	if (ioctl(kdvm_fd, KDVDCTYPE, &vdctype) < 0) {
		report_fail("kdvm", "KDVDCTYPE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDVDCTYPE controller=%s display=%s",
			lookup_name(display_types, ARRAY_SIZE(display_types), (int)vdctype.cntlr),
			lookup_name(monitor_types, ARRAY_SIZE(monitor_types), (int)vdctype.dsply));
		report_pass("kdvm", detail);
	}

	if (ioctl(kdvm_fd, KDDISPINFO, &dispinfo) < 0) {
		report_fail("kdvm", "KDDISPINFO");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDDISPINFO phys=0x%08lx size=%lu", dispinfo.physaddr, dispinfo.size);
		report_pass("kdvm", detail);
	}

	if (fetch_console_adapter_value(kdvm_fd, &console_adapter) < 0) {
		report_fail("kdvm", "CONS_CURRENT");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "CONS_CURRENT adapter=%s",
			lookup_name(display_types, ARRAY_SIZE(display_types), console_adapter));
		report_pass("kdvm", detail);
		if (adapter_type_out)
			*adapter_type_out = console_adapter;
	}

	if (fetch_console_mode_value(kdvm_fd, &console_mode) < 0) {
		report_fail("kdvm", "CONS_GET");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "CONS_GET mode=%s (0x%x)",
			lookup_name(console_modes, ARRAY_SIZE(console_modes), console_mode), console_mode);
		report_pass("kdvm", detail);
	}

	if (fetch_text_graphics_mode(kdvm_fd, &text_graphics_mode) < 0) {
		report_fail("kdvm", "KDGETMODE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDGETMODE mode=%s", text_graphics_mode == KD_GRAPHICS ? "graphics" : (text_graphics_mode == KD_TEXT1 ? "text1" : "text0"));
		report_pass("kdvm", detail);
	}

	if (ioctl(kdvm_fd, KDSBORDER, 0) < 0)
		report_skip("kdvm", "KDSBORDER unsupported on current adapter or mode");
	else
		report_pass("kdvm", "KDSBORDER set border to black");

	if (ioctl(kdvm_fd, KIOCSOUND, 1331) < 0) {
		report_fail("kdvm", "KIOCSOUND start");
		++failures;
	} else {
		usleep(100000);
		if (ioctl(kdvm_fd, KIOCSOUND, 0) < 0) {
			report_fail("kdvm", "KIOCSOUND stop");
			++failures;
		} else {
			report_pass("kdvm", "KIOCSOUND start/stop");
		}
	}

	if (ioctl(kdvm_fd, KDMKTONE, (150 << 16) | 1331) < 0) {
		report_fail("kdvm", "KDMKTONE");
		++failures;
	} else {
		report_pass("kdvm", "KDMKTONE 150ms tone");
	}

	probe_port = pick_probe_port(&disparam);
	if (!probe_port) {
		report_skip("kdvm", "KDADDIO/KDENABIO skipped because no probe port was reported");
	} else {
		if (ioctl(kdvm_fd, KDADDIO, (unsigned int)probe_port) < 0) {
			report_fail("kdvm", "KDADDIO");
			++failures;
		} else {
			report_pass("kdvm", "KDADDIO added probe port");
			if (ioctl(kdvm_fd, KDENABIO, 0) < 0) {
				report_fail("kdvm", "KDENABIO");
				++failures;
			} else {
				report_pass("kdvm", "KDENABIO");
			}
			if (ioctl(kdvm_fd, KDDISABIO, 0) < 0) {
				report_fail("kdvm", "KDDISABIO");
				++failures;
			} else {
				report_pass("kdvm", "KDDISABIO");
			}
			if (ioctl(kdvm_fd, KDDELIO, (unsigned int)probe_port) < 0) {
				report_fail("kdvm", "KDDELIO");
				++failures;
			} else {
				report_pass("kdvm", "KDDELIO removed probe port");
			}
		}
	}

	return failures;
}

static int run_video_queries(int video_fd)
{
	struct kd_disparam disparam;
	struct kd_dispinfo dispinfo;
	int console_adapter;
	int console_mode;
	int text_graphics_mode;
	int failures;
	char detail[224];

	failures = 0;
	if (video_fd < 0) {
		report_skip("video", "device node not present");
		return 0;
	}

	memset(&disparam, 0, sizeof(disparam));
	if (ioctl(video_fd, KDDISPTYPE, &disparam) < 0) {
		report_fail("video", "KDDISPTYPE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDDISPTYPE type=%s addr=%p",
			lookup_name(display_types, ARRAY_SIZE(display_types), (int)disparam.type), disparam.addr);
		report_pass("video", detail);
	}

	if (ioctl(video_fd, KDDISPINFO, &dispinfo) < 0) {
		report_fail("video", "KDDISPINFO");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDDISPINFO phys=0x%08lx size=%lu", dispinfo.physaddr, dispinfo.size);
		report_pass("video", detail);
	}

	if (fetch_console_adapter_value(video_fd, &console_adapter) < 0) {
		report_fail("video", "CONS_CURRENT");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "CONS_CURRENT adapter=%s",
			lookup_name(display_types, ARRAY_SIZE(display_types), console_adapter));
		report_pass("video", detail);
	}

	if (fetch_console_mode_value(video_fd, &console_mode) < 0) {
		report_fail("video", "CONS_GET");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "CONS_GET mode=%s (0x%x)",
			lookup_name(console_modes, ARRAY_SIZE(console_modes), console_mode), console_mode);
		report_pass("video", detail);
	}

	if (fetch_text_graphics_mode(video_fd, &text_graphics_mode) < 0) {
		report_fail("video", "KDGETMODE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "KDGETMODE mode=%s", text_graphics_mode == KD_GRAPHICS ? "graphics" : (text_graphics_mode == KD_TEXT1 ? "text1" : "text0"));
		report_pass("video", detail);
	}

	return failures;
}

static int run_vidadm_queries(int vidadm_fd)
{
	gvid_t mapping;
	dev_t devices[16];
	int failures;
	char detail[160];

	failures = 0;
	if (vidadm_fd < 0) {
		report_skip("vidadm", "device node not present");
		return 0;
	}

	memset(&mapping, 0, sizeof(mapping));
	mapping.gvid_num = ARRAY_SIZE(devices);
	mapping.gvid_buf = devices;
	if (ioctl(vidadm_fd, GVID_GETTABLE, &mapping) < 0) {
		report_fail("vidadm", "GVID_GETTABLE");
		++failures;
	} else {
		snprintf(detail, sizeof(detail), "GVID_GETTABLE entries=%lu major=%u", mapping.gvid_num, mapping.gvid_maj);
		report_pass("vidadm", detail);
		if (ioctl(vidadm_fd, GVID_SETTABLE, &mapping) < 0) {
			report_fail("vidadm", "GVID_SETTABLE round-trip");
			++failures;
		} else {
			report_pass("vidadm", "GVID_SETTABLE round-trip");
		}
	}

	return failures;
}

static int run_queue_test(int kdvm_fd, int queue_seconds)
{
	struct kd_quemode quemode;
	volatile struct xqEventQueue *queue;
	int failures;
	int pending;
	int head;
	int tail;
	int count;
	int index;
	char detail[160];

	failures = 0;
	memset(&quemode, 0, sizeof(quemode));
	quemode.qsize = 128;
	quemode.signo = 0;

	if (ioctl(kdvm_fd, KDQUEMODE, &quemode) < 0) {
		report_fail("queue", "KDQUEMODE enable");
		return 1;
	}

	queue = (volatile struct xqEventQueue *)quemode.qaddr;
	if (!queue) {
		report_fail("queue", "driver returned a null queue address");
		(void)ioctl(kdvm_fd, KDQUEMODE, 0);
		return 1;
	}

	snprintf(detail, sizeof(detail), "KDQUEMODE enabled qaddr=%p qsize=%d; press keys or move the mouse for %d seconds",
		quemode.qaddr, queue->xq_size, queue_seconds);
	report_pass("queue", detail);

	sleep((unsigned int)queue_seconds);

	head = queue->xq_head;
	tail = queue->xq_tail;
	if (tail >= head)
		pending = tail - head;
	else
		pending = queue->xq_size - (head - tail);

	snprintf(detail, sizeof(detail), "queue head=%d tail=%d pending=%d", head, tail, pending);
	report_pass("queue", detail);

	count = pending < 8 ? pending : 8;
	for (index = 0; index < count; ++index) {
		int slot;
		const volatile struct xqEvent *event;

		slot = (head + index) % queue->xq_size;
		event = &queue->xq_events[slot];
		printf("[PASS] queue sample[%d] type=%s code=0x%x dx=%d dy=%d time=%ld\n",
			index, event_type_name(event->xq_type), event->xq_code,
			event->xq_x, event->xq_y, (long)event->xq_time);
	}

	if (ioctl(kdvm_fd, KDQUEMODE, 0) < 0) {
		report_fail("queue", "KDQUEMODE disable");
		++failures;
	} else {
		report_pass("queue", "KDQUEMODE disable");
	}

	return failures;
}

static const struct graphics_mode *choose_default_graphics_mode(int adapter_type)
{
	switch (adapter_type) {
	case KD_VGA:
		return find_graphics_mode("vga320x200");
	case KD_VDC600:
		return find_graphics_mode("vdc640x400v");
	case KD_VDC400:
	case KD_VDC750:
		return find_graphics_mode("att640");
	case KD_EGA:
		return find_graphics_mode("cg640x350");
	case KD_CGA:
		return find_graphics_mode("cg320");
	default:
		return NULL;
	}
}

int main(int argc, char **argv)
{
	struct options options;
	struct device_handles devices;
	struct kd_disparam disparam;
	const struct graphics_mode *graphics_mode;
	int adapter_type;
	int failures;
	int parse_result;

	setvbuf(stdout, NULL, _IONBF, 0);
	setvbuf(stderr, NULL, _IONBF, 0);

	parse_result = parse_options(argc, argv, &options);
	if (parse_result > 0)
		return 0;
	if (parse_result < 0)
		return 2;

	if (geteuid() != 0)
		printf("[SKIP] preflight not running as root; privileged ioctls may fail\n");

	if (open_devices(&devices) < 0) {
		fprintf(stderr, "failed to open required workstation devices: %s\n", strerror(errno));
		close_devices(&devices);
		return 1;
	}

	printf("[PASS] preflight vt=%s stream=%s kdvm=%s\n",
		devices.vt_path, devices.stream_path, devices.kdvm_path);
	if (devices.video_fd >= 0)
		printf("[PASS] preflight video=%s\n", devices.video_path);
	else
		printf("[SKIP] preflight /dev/video not available: %s\n", strerror(errno));
	if (devices.vidadm_fd >= 0)
		printf("[PASS] preflight vidadm=%s\n", devices.vidadm_path);
	else
		printf("[SKIP] preflight /dev/vidadm not available: %s\n", strerror(errno));

	memset(&disparam, 0, sizeof(disparam));
	adapter_type = -1;
	failures = 0;

	failures += run_console_queries(devices.vt_fd, devices.stream_fd);
	failures += run_kdvm_queries(devices.kdvm_fd, &disparam, &adapter_type);
	if (options.run_video)
		failures += run_video_queries(devices.video_fd);
	if (options.run_admin)
		failures += run_vidadm_queries(devices.vidadm_fd);
	if (options.run_queue)
		failures += run_queue_test(devices.kdvm_fd, options.queue_seconds);

	graphics_mode = options.graphics_mode;
	if (options.run_graphics && options.choose_default_graphics)
		graphics_mode = choose_default_graphics_mode(adapter_type);

	if (options.run_graphics) {
		if (!graphics_mode) {
			report_skip("graphics", "no default graphics mode is known for this adapter");
			++failures;
		} else {
			printf("[PASS] graphics selected mode=%s\n", graphics_mode->name);
			failures += run_graphics_mode_test(devices.kdvm_fd, graphics_mode,
				options.timeout_seconds, options.hold_seconds);
		}
	}

	close_devices(&devices);
	return failures ? 1 : 0;
}