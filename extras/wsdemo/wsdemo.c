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
#include <time.h>
#include <unistd.h>

typedef unsigned char unchar;
typedef unsigned short ushort;

#define ARRAY_SIZE(array) (sizeof(array) / sizeof((array)[0]))

#define VTIOC ('v' << 8)
#define VT_SETMODE (VTIOC | 2)
#define VT_RELDISP (VTIOC | 4)

#define VT_AUTO 0
#define VT_PROCESS 1
#define VT_ACKACQ 2

#define KIOC ('K' << 8)
#define KDDISPTYPE (KIOC | 1)
#define KDMAPDISP (KIOC | 2)
#define KDUNMAPDISP (KIOC | 3)
#define KDGETMODE (KIOC | 9)
#define KDSETMODE (KIOC | 10)
#define KDADDIO (KIOC | 11)
#define KDDELIO (KIOC | 12)
#define KDQUEMODE (KIOC | 15)
#define KDDISPINFO (KIOC | 18)
#define KDENABIO (KIOC | 60)
#define KDDISABIO (KIOC | 61)

#define MODESWITCH ('x' << 8)
#define MAPADAPTER ('m' << 8)

#define MAPCONS (MAPADAPTER)
#define MAPCGA (MAPADAPTER | 2)
#define MAPEGA (MAPADAPTER | 4)
#define MAPVGA (MAPADAPTER | 5)

#define CONSIOC ('c' << 8)
#define CONS_CURRENT (CONSIOC | 1)
#define CONS_GET (CONSIOC | 2)

#define KD_CGA 3
#define KD_EGA 4
#define KD_VGA 5
#define KD_VDC400 6
#define KD_VDC750 7
#define KD_VDC600 8

#define KD_TEXT0 0
#define KD_GRAPHICS 1
#define KD_TEXT1 2

#define DM_CG320 5
#define DM_CG640x350 16
#define DM_ATT_640 34
#define DM_VGA320x200 28
#define DM_VDC800x600E 39
#define DM_VDC640x400V 40

#define SW_CG320 (MODESWITCH | DM_CG320)
#define SW_CG640x350 (MODESWITCH | DM_CG640x350)
#define SW_ATT640 (MODESWITCH | DM_ATT_640)
#define SW_VGA320x200 (MODESWITCH | DM_VGA320x200)
#define SW_VDC800x600E (MODESWITCH | DM_VDC800x600E)
#define SW_VDC640x400V (MODESWITCH | DM_VDC640x400V)

#define XQ_BUTTON 0
#define XQ_MOTION 1
#define XQ_KEY 2

struct vt_mode {
	char mode;
	char waitv;
	short relsig;
	short acqsig;
	short frsig;
};

struct kd_disparam {
	long type;
	char *addr;
	ushort ioaddr[64];
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

enum draw_kind {
	DRAW_LINEAR8,
	DRAW_PLANAR4,
};

struct graphics_mode {
	const char *name;
	int switch_ioctl;
	int map_ioctl;
	int width;
	int height;
	int depth_bits;
	size_t bank_size;
	enum draw_kind draw_kind;
};

struct options {
	const struct graphics_mode *mode;
	int seconds;
};

struct runtime_state {
	int vt_fd;
	int kdvm_fd;
	const struct graphics_mode *mode;
	int original_console_mode;
	int original_text_graphics_mode;
	volatile unsigned char *framebuffer;
	unsigned char *backbuffer;
	void *mapping_base;
	size_t mapping_size;
	size_t backbuffer_size;
	size_t framebuffer_size;
	int framebuffer_stride;
	int scene_dirty;
	int queue_enabled;
	int io_enabled;
	volatile struct xqEventQueue *queue;
	int display_mapped;
	int graphics_active;
	int vt_process_mode;
	int cursor_x;
	int cursor_y;
	unsigned int key_events;
	unsigned int button_events;
	unsigned int motion_events;
	unsigned int last_key_code;
	unsigned int button_state;
	unsigned int vt_releases;
	unsigned int vt_acquires;
};

static const struct graphics_mode graphics_modes[] = {
	{"vga320x200", SW_VGA320x200, MAPVGA, 320, 200, 8, 0, DRAW_LINEAR8},
	{"vdc640x400v", SW_VDC640x400V, MAPCONS, 640, 400, 8, 0, DRAW_LINEAR8},
	{"vdc800x600e", SW_VDC800x600E, MAPCONS, 800, 600, 4, 64 * 1024U, DRAW_PLANAR4},
};

static struct runtime_state runtime_state;
static volatile sig_atomic_t release_requested;
static volatile sig_atomic_t acquire_requested;
static volatile sig_atomic_t terminate_requested;

static void unmap_display_memory(void);

static const unsigned short vga_io_ports[] = {0x3c4, 0x3c5, 0x3ce, 0x3cf};

static inline void write_port8(unsigned short port, unsigned char value)
{
	__asm__ __volatile__("outb %0, %1" : : "a"(value), "Nd"(port));
}

static int enable_vga_io(void)
{
	size_t index;

	if (runtime_state.io_enabled)
		return 0;

	for (index = 0; index < ARRAY_SIZE(vga_io_ports); ++index) {
		if (ioctl(runtime_state.kdvm_fd, KDADDIO, (unsigned int)vga_io_ports[index]) < 0)
			goto fail;
	}

	if (ioctl(runtime_state.kdvm_fd, KDENABIO, 0) < 0)
		goto fail;

	runtime_state.io_enabled = 1;
	return 0;

fail:
	(void)ioctl(runtime_state.kdvm_fd, KDDISABIO, 0);
	while (index > 0) {
		--index;
		(void)ioctl(runtime_state.kdvm_fd, KDDELIO, (unsigned int)vga_io_ports[index]);
	}
	return -1;
}

static void disable_vga_io(void)
{
	size_t index;

	if (!runtime_state.io_enabled)
		return;

	(void)ioctl(runtime_state.kdvm_fd, KDDISABIO, 0);
	for (index = ARRAY_SIZE(vga_io_ports); index > 0; --index)
		(void)ioctl(runtime_state.kdvm_fd, KDDELIO, (unsigned int)vga_io_ports[index - 1]);
	runtime_state.io_enabled = 0;
}

static void vga_write_register(unsigned short index_port, unsigned short data_port, unsigned char index, unsigned char value)
{
	write_port8(index_port, index);
	write_port8(data_port, value);
}

static void set_vga_plane_mask(unsigned char plane_mask)
{
	vga_write_register(0x3c4, 0x3c5, 0x02, plane_mask);
}

static void set_vga_byte_mask(unsigned char byte_mask)
{
	vga_write_register(0x3ce, 0x3cf, 0x08, byte_mask);
}

static void print_usage(const char *program)
{
	printf("usage: %s [--mode NAME] [--seconds SEC] [--list-modes]\n", program);
}

static void list_modes(void)
{
	size_t index;

	for (index = 0; index < ARRAY_SIZE(graphics_modes); ++index)
		printf("%s\n", graphics_modes[index].name);
}

static const struct graphics_mode *find_mode(const char *name)
{
	size_t index;

	for (index = 0; index < ARRAY_SIZE(graphics_modes); ++index) {
		if (!strcmp(graphics_modes[index].name, name))
			return &graphics_modes[index];
	}

	return NULL;
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
	options->seconds = 15;

	for (index = 1; index < argc; ++index) {
		if (!strcmp(argv[index], "--help")) {
			print_usage(argv[0]);
			return 1;
		}
		if (!strcmp(argv[index], "--list-modes")) {
			list_modes();
			return 1;
		}
		if (!strcmp(argv[index], "--mode")) {
			if (index + 1 >= argc) {
				fprintf(stderr, "--mode requires a value\n");
				return -1;
			}
			options->mode = find_mode(argv[++index]);
			if (!options->mode) {
				fprintf(stderr, "unknown mode: %s\n", argv[index]);
				return -1;
			}
			continue;
		}
		if (!strncmp(argv[index], "--mode=", 7)) {
			options->mode = find_mode(argv[index] + 7);
			if (!options->mode) {
				fprintf(stderr, "unknown mode: %s\n", argv[index] + 7);
				return -1;
			}
			continue;
		}
		if (!strcmp(argv[index], "--seconds")) {
			if (index + 1 >= argc || parse_positive_int(argv[++index], &options->seconds)) {
				fprintf(stderr, "invalid --seconds value\n");
				return -1;
			}
			continue;
		}

		fprintf(stderr, "unknown option: %s\n", argv[index]);
		return -1;
	}

	return 0;
}

static int open_first_rw(const char *const *paths, size_t count)
{
	size_t index;
	int fd;

	for (index = 0; index < count; ++index) {
		fd = open(paths[index], O_RDWR);
		if (fd >= 0)
			return fd;
	}

	return -1;
}

static void close_if_open(int *fd)
{
	if (*fd >= 0) {
		close(*fd);
		*fd = -1;
	}
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

static int fetch_text_graphics_mode(int fd, int *mode_value)
{
	if (ioctl(fd, KDGETMODE, mode_value) < 0)
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

static const struct graphics_mode *choose_default_mode(int adapter_type)
{
	switch (adapter_type) {
	case KD_VGA:
		return find_mode("vga320x200");
	case KD_VDC600:
		return find_mode("vdc800x600e");
	default:
		return NULL;
	}
}

static void print_mode_details(int seconds)
{
	printf("wsdemo: mode=%s %dx%d %dbpp framebuffer=%lu stride=%d bank=%lu duration=%d seconds\n",
		runtime_state.mode->name,
		runtime_state.mode->width,
		runtime_state.mode->height,
		runtime_state.mode->depth_bits,
		(unsigned long)runtime_state.framebuffer_size,
		runtime_state.framebuffer_stride,
		(unsigned long)runtime_state.mode->bank_size,
		seconds);
}

static void on_release_signal(int signo)
{
	(void)signo;
	release_requested = 1;
}

static void on_acquire_signal(int signo)
{
	(void)signo;
	acquire_requested = 1;
}

static void on_terminate_signal(int signo)
{
	(void)signo;
	terminate_requested = 1;
}

static int install_signal_handler(int signo, void (*handler)(int))
{
	struct sigaction action;

	memset(&action, 0, sizeof(action));
	action.sa_handler = handler;
	if (sigemptyset(&action.sa_mask) < 0)
		return -1;
	return sigaction(signo, &action, NULL);
}

static int install_signal_handlers(void)
{
	if (install_signal_handler(SIGUSR1, on_release_signal) < 0)
		return -1;
	if (install_signal_handler(SIGUSR2, on_acquire_signal) < 0)
		return -1;
	if (install_signal_handler(SIGINT, on_terminate_signal) < 0)
		return -1;
	if (install_signal_handler(SIGTERM, on_terminate_signal) < 0)
		return -1;
	if (install_signal_handler(SIGHUP, on_terminate_signal) < 0)
		return -1;
	return 0;
}

static int set_vt_process_mode(int vt_fd)
{
	struct vt_mode vtmode;

	memset(&vtmode, 0, sizeof(vtmode));
	vtmode.mode = VT_PROCESS;
	vtmode.relsig = SIGUSR1;
	vtmode.acqsig = SIGUSR2;
	vtmode.frsig = SIGUSR1;
	if (ioctl(vt_fd, VT_SETMODE, &vtmode) < 0)
		return -1;

	runtime_state.vt_process_mode = 1;
	return 0;
}

static void set_vt_auto_mode(void)
{
	struct vt_mode vtmode;

	if (!runtime_state.vt_process_mode || runtime_state.vt_fd < 0)
		return;

	memset(&vtmode, 0, sizeof(vtmode));
	vtmode.mode = VT_AUTO;
	(void)ioctl(runtime_state.vt_fd, VT_SETMODE, &vtmode);
	runtime_state.vt_process_mode = 0;
}

static int map_display_memory(void)
{
	struct kd_dispinfo dispinfo;
	struct kd_memloc memloc;
	size_t backbuffer_size;
	void *mapping_base;
	size_t mapping_size;

	if (ioctl(runtime_state.kdvm_fd, KDDISPINFO, &dispinfo) < 0)
		return -1;

	mapping_size = round_up_page_size((size_t)dispinfo.size);
	mapping_base = reserve_mapping_address(mapping_size);
	if (!mapping_base) {
		errno = ENOMEM;
		return -1;
	}

	memset(&memloc, 0, sizeof(memloc));
	memloc.vaddr = (char *)mapping_base;
	memloc.physaddr = (char *)(uintptr_t)dispinfo.physaddr;
	memloc.length = (long)dispinfo.size;
	memloc.ioflg = 1;

	if (ioctl(runtime_state.kdvm_fd, KDMAPDISP, &memloc) < 0)
		return -1;

	runtime_state.framebuffer = (volatile unsigned char *)memloc.vaddr;
	runtime_state.mapping_base = mapping_base;
	runtime_state.mapping_size = mapping_size;
	runtime_state.framebuffer_size = (size_t)dispinfo.size;
	runtime_state.display_mapped = 1;
	if (runtime_state.mode->depth_bits == 4)
		runtime_state.framebuffer_stride = (runtime_state.mode->width + 7) / 8;
	else
		runtime_state.framebuffer_stride = runtime_state.mode->width;

	backbuffer_size = (size_t)runtime_state.mode->width * (size_t)runtime_state.mode->height;
	if (runtime_state.mode->height > 0 && backbuffer_size / (size_t)runtime_state.mode->height != (size_t)runtime_state.mode->width) {
		errno = EOVERFLOW;
		return -1;
	}
	runtime_state.backbuffer_size = backbuffer_size;

	runtime_state.backbuffer = malloc(runtime_state.backbuffer_size);
	if (!runtime_state.backbuffer) {
		unmap_display_memory();
		errno = ENOMEM;
		return -1;
	}

	memset(runtime_state.backbuffer, 0, runtime_state.backbuffer_size);

	return 0;
}

static void unmap_display_memory(void)
{
	if (!runtime_state.display_mapped)
		return;

	(void)ioctl(runtime_state.kdvm_fd, KDUNMAPDISP, 0);
	if (runtime_state.mapping_base && runtime_state.mapping_size)
		(void)munmap(runtime_state.mapping_base, runtime_state.mapping_size);
	runtime_state.framebuffer = NULL;
	free(runtime_state.backbuffer);
	runtime_state.backbuffer = NULL;
	runtime_state.mapping_base = NULL;
	runtime_state.mapping_size = 0;
	runtime_state.backbuffer_size = 0;
	runtime_state.framebuffer_size = 0;
	runtime_state.scene_dirty = 0;
	runtime_state.display_mapped = 0;
	}

static int enable_queue_mode(void)
{
	struct kd_quemode quemode;

	memset(&quemode, 0, sizeof(quemode));
	quemode.qsize = 256;
	if (ioctl(runtime_state.kdvm_fd, KDQUEMODE, &quemode) < 0)
		return -1;
	if (!quemode.qaddr) {
		(void)ioctl(runtime_state.kdvm_fd, KDQUEMODE, 0);
		errno = EIO;
		return -1;
	}

	runtime_state.queue = (volatile struct xqEventQueue *)quemode.qaddr;
	runtime_state.queue_enabled = 1;
	return 0;
}

static void disable_queue_mode(void)
{
	if (!runtime_state.queue_enabled)
		return;

	(void)ioctl(runtime_state.kdvm_fd, KDQUEMODE, 0);
	runtime_state.queue = NULL;
	runtime_state.queue_enabled = 0;
}

static void put_pixel_shadow(int x, int y, unsigned char color)
{
	size_t offset;

	if (!runtime_state.backbuffer)
		return;
	if (x < 0 || y < 0 || x >= runtime_state.mode->width || y >= runtime_state.mode->height)
		return;
	offset = (size_t)y * (size_t)runtime_state.mode->width + (size_t)x;
	if (offset >= runtime_state.backbuffer_size)
		return;
	runtime_state.backbuffer[offset] = color;
}

static void fill_rect_linear8(int x, int y, int width, int height, unsigned char color)
{
	int px;
	int py;

	for (py = 0; py < height; ++py) {
		for (px = 0; px < width; ++px)
			put_pixel_shadow(x + px, y + py, color);
	}
}

static void draw_line_linear8(int x0, int y0, int x1, int y1, unsigned char color)
{
	int dx;
	int dy;
	int step_x;
	int step_y;
	int error;
	int error2;

	dx = abs(x1 - x0);
	dy = abs(y1 - y0);
	step_x = x0 < x1 ? 1 : -1;
	step_y = y0 < y1 ? 1 : -1;
	error = dx - dy;

	for (;;) {
		put_pixel_shadow(x0, y0, color);
		if (x0 == x1 && y0 == y1)
			break;
		error2 = error * 2;
		if (error2 > -dy) {
			error -= dy;
			x0 += step_x;
		}
		if (error2 < dx) {
			error += dx;
			y0 += step_y;
		}
	}
}

static void draw_scene_indexed(unsigned char color_mask)
{
	int x;
	int y;
	unsigned char phase;
	int bar_width;

	if (!runtime_state.backbuffer)
		return;

	phase = (unsigned char)((runtime_state.motion_events + runtime_state.button_events * 5U + runtime_state.key_events * 11U) & 0xffU);
	for (y = 0; y < runtime_state.mode->height; ++y) {
		for (x = 0; x < runtime_state.mode->width; ++x) {
			size_t offset;
			unsigned char color;

			offset = (size_t)y * (size_t)runtime_state.mode->width + (size_t)x;
			if (offset >= runtime_state.backbuffer_size)
				break;
			color = (unsigned char)(((x >> 2) + (y >> 1) + phase) & color_mask);
			if (!(x % 32) || !(y % 24))
				color = (unsigned char)((phase ^ 0x20U) & color_mask);
			runtime_state.backbuffer[offset] = color;
		}
	}

	fill_rect_linear8(8, 8, runtime_state.mode->width - 16, 12, (unsigned char)(0x1f & color_mask));
	fill_rect_linear8(8, runtime_state.mode->height - 20, runtime_state.mode->width - 16, 12, (unsigned char)(0x08 & color_mask));
	draw_line_linear8(0, 0, runtime_state.mode->width - 1, runtime_state.mode->height - 1, (unsigned char)(0xff & color_mask));
	draw_line_linear8(0, runtime_state.mode->height - 1, runtime_state.mode->width - 1, 0, (unsigned char)(0xe0 & color_mask));

	bar_width = runtime_state.mode->width - 20;
	if (bar_width < 1)
		bar_width = 1;
	fill_rect_linear8(10, runtime_state.mode->height - 18,
		(int)(runtime_state.motion_events % (unsigned int)bar_width), 3, (unsigned char)(0x40 & color_mask));
	fill_rect_linear8(10, runtime_state.mode->height - 13,
		(int)(runtime_state.button_events % (unsigned int)bar_width), 3, (unsigned char)(0xa0 & color_mask));
	fill_rect_linear8(10, runtime_state.mode->height - 8,
		(int)(runtime_state.key_events % (unsigned int)bar_width), 3, (unsigned char)(0xf0 & color_mask));

	fill_rect_linear8(runtime_state.cursor_x - 3, runtime_state.cursor_y - 3, 7, 7,
		(unsigned char)(((runtime_state.button_state & 0x01U) ? 0x1c : 0xfc) & color_mask));
	draw_line_linear8(runtime_state.cursor_x - 10, runtime_state.cursor_y,
		runtime_state.cursor_x + 10, runtime_state.cursor_y, (unsigned char)(0xff & color_mask));
	draw_line_linear8(runtime_state.cursor_x, runtime_state.cursor_y - 10,
		runtime_state.cursor_x, runtime_state.cursor_y + 10, (unsigned char)(0xff & color_mask));
}

static void blit_planar4_scene(void)
{
	volatile unsigned char *framebuffer;
	size_t row_bytes;
	size_t plane;
	size_t y;
	size_t xbyte;
	size_t width;
	size_t height;
	size_t framebuffer_stride;

	if (!runtime_state.backbuffer || !runtime_state.framebuffer)
		return;

	framebuffer = runtime_state.framebuffer;
	width = (size_t)runtime_state.mode->width;
	height = (size_t)runtime_state.mode->height;
	framebuffer_stride = (size_t)runtime_state.framebuffer_stride;
	row_bytes = (width + 7U) / 8U;

	set_vga_byte_mask(0xff);
	for (plane = 0; plane < 4; ++plane) {
		set_vga_plane_mask((unsigned char)(1U << plane));
		for (y = 0; y < height; ++y) {
			const unsigned char *source_row;
			volatile unsigned char *destination_row;

			source_row = runtime_state.backbuffer + (y * width);
			destination_row = framebuffer + (y * framebuffer_stride);
			for (xbyte = 0; xbyte < row_bytes; ++xbyte) {
				unsigned char value;
				size_t bit;

				value = 0;
				for (bit = 0; bit < 8; ++bit) {
					size_t pixel_x;
					unsigned char color;

					pixel_x = (xbyte * 8U) + bit;
					if (pixel_x >= width)
						break;
					color = source_row[pixel_x];
					if (color & (1U << plane))
						value |= (unsigned char)(1U << (7U - bit));
				}
				destination_row[xbyte] = value;
			}
		}
	}
	set_vga_plane_mask(0x0f);
}

static void redraw_scene(void)
{
	if (!runtime_state.graphics_active || !runtime_state.framebuffer)
		return;
	if (!runtime_state.scene_dirty)
		return;

	if (runtime_state.mode->draw_kind == DRAW_LINEAR8) {
		draw_scene_indexed(0xff);
		memcpy((void *)runtime_state.framebuffer, runtime_state.backbuffer,
			runtime_state.backbuffer_size < runtime_state.framebuffer_size ? runtime_state.backbuffer_size : runtime_state.framebuffer_size);
	} else if (runtime_state.mode->draw_kind == DRAW_PLANAR4) {
		draw_scene_indexed(0x0f);
		blit_planar4_scene();
	}

	runtime_state.scene_dirty = 0;
}

static int enter_graphics_mode(void)
{
	if (ioctl(runtime_state.kdvm_fd, runtime_state.mode->switch_ioctl, 0) < 0)
		return -1;
	if (ioctl(runtime_state.kdvm_fd, KDSETMODE, KD_GRAPHICS) < 0)
		return -1;
	if (map_display_memory() < 0) {
		(void)restore_display_mode(runtime_state.kdvm_fd,
			runtime_state.original_console_mode,
			runtime_state.original_text_graphics_mode);
		return -1;
	}
	if (runtime_state.mode->draw_kind == DRAW_PLANAR4 && enable_vga_io() < 0) {
		unmap_display_memory();
		(void)restore_display_mode(runtime_state.kdvm_fd,
			runtime_state.original_console_mode,
			runtime_state.original_text_graphics_mode);
		return -1;
	}
	if (enable_queue_mode() < 0) {
		disable_vga_io();
		unmap_display_memory();
		(void)restore_display_mode(runtime_state.kdvm_fd,
			runtime_state.original_console_mode,
			runtime_state.original_text_graphics_mode);
		return -1;
	}

	runtime_state.graphics_active = 1;
	runtime_state.cursor_x = runtime_state.mode->width / 2;
	runtime_state.cursor_y = runtime_state.mode->height / 2;
	runtime_state.scene_dirty = 1;
	redraw_scene();
	return 0;
}

static void leave_graphics_mode(void)
{
	disable_queue_mode();
	disable_vga_io();
	unmap_display_memory();
	if (runtime_state.graphics_active) {
		(void)restore_display_mode(runtime_state.kdvm_fd,
			runtime_state.original_console_mode,
			runtime_state.original_text_graphics_mode);
		runtime_state.graphics_active = 0;
	}
}

static void clamp_cursor(void)
{
	if (runtime_state.cursor_x < 0)
		runtime_state.cursor_x = 0;
	if (runtime_state.cursor_y < 0)
		runtime_state.cursor_y = 0;
	if (runtime_state.cursor_x >= runtime_state.mode->width)
		runtime_state.cursor_x = runtime_state.mode->width - 1;
	if (runtime_state.cursor_y >= runtime_state.mode->height)
		runtime_state.cursor_y = runtime_state.mode->height - 1;
}

static void handle_queue_event(const struct xqEvent *event)
{
	switch (event->xq_type) {
	case XQ_MOTION:
		runtime_state.motion_events++;
		runtime_state.cursor_x += event->xq_x;
		runtime_state.cursor_y -= event->xq_y;
		clamp_cursor();
		runtime_state.scene_dirty = 1;
		break;
	case XQ_BUTTON:
		runtime_state.button_events++;
		runtime_state.button_state = event->xq_code;
		runtime_state.scene_dirty = 1;
		break;
	case XQ_KEY:
		runtime_state.key_events++;
		runtime_state.last_key_code = event->xq_code;
		runtime_state.scene_dirty = 1;
		if (!(event->xq_code & 0x80U)) {
			if ((event->xq_code & 0x7fU) == 0x01U || (event->xq_code & 0x7fU) == 0x10U)
				terminate_requested = 1;
		}
		break;
	default:
		break;
	}
}

static void consume_queue_events(void)
{
	while (runtime_state.queue && runtime_state.queue->xq_head != runtime_state.queue->xq_tail) {
		int head;
		struct xqEvent event;

		head = runtime_state.queue->xq_head;
		event = runtime_state.queue->xq_events[head];
		handle_queue_event(&event);
		runtime_state.queue->xq_head = (head + 1) % runtime_state.queue->xq_size;
	}
}

static void handle_vt_transitions(void)
{
	if (release_requested) {
		release_requested = 0;
		if (runtime_state.graphics_active) {
			leave_graphics_mode();
			if (ioctl(runtime_state.vt_fd, VT_RELDISP, 1) >= 0)
				runtime_state.vt_releases++;
		}
	}

	if (acquire_requested) {
		acquire_requested = 0;
		if (ioctl(runtime_state.vt_fd, VT_RELDISP, VT_ACKACQ) >= 0)
			runtime_state.vt_acquires++;
		if (!runtime_state.graphics_active && enter_graphics_mode() < 0)
			terminate_requested = 1;
	}
}

static void cleanup_runtime(void)
{
	leave_graphics_mode();
	set_vt_auto_mode();
	close_if_open(&runtime_state.kdvm_fd);
	close_if_open(&runtime_state.vt_fd);
}

int main(int argc, char **argv)
{
	static const char *const vt_paths[] = {"/dev/vt00", "/dev/tty", "/dev/syscon", "/dev/console"};
	static const char *const kdvm_paths[] = {"/dev/kd/kdvm00", "/dev/video"};
	struct options options;
	int parse_result;
	int adapter_type;
	time_t deadline;

	memset(&runtime_state, 0, sizeof(runtime_state));
	runtime_state.vt_fd = -1;
	runtime_state.kdvm_fd = -1;

	parse_result = parse_options(argc, argv, &options);
	if (parse_result > 0)
		return 0;
	if (parse_result < 0)
		return 2;

	runtime_state.vt_fd = open_first_rw(vt_paths, ARRAY_SIZE(vt_paths));
	if (runtime_state.vt_fd < 0) {
		fprintf(stderr, "wsdemo: unable to open a VT device: %s\n", strerror(errno));
		return 1;
	}

	runtime_state.kdvm_fd = open_first_rw(kdvm_paths, ARRAY_SIZE(kdvm_paths));
	if (runtime_state.kdvm_fd < 0) {
		fprintf(stderr, "wsdemo: unable to open a display device: %s\n", strerror(errno));
		cleanup_runtime();
		return 1;
	}

	if (fetch_console_mode_value(runtime_state.kdvm_fd, &runtime_state.original_console_mode) < 0
			|| fetch_text_graphics_mode(runtime_state.kdvm_fd, &runtime_state.original_text_graphics_mode) < 0) {
		fprintf(stderr, "wsdemo: unable to read current display mode: %s\n", strerror(errno));
		cleanup_runtime();
		return 1;
	}

	if (options.mode) {
		runtime_state.mode = options.mode;
	} else {
		adapter_type = 0;
		if (fetch_console_adapter_value(runtime_state.kdvm_fd, &adapter_type) < 0) {
			struct kd_disparam disparam;

			memset(&disparam, 0, sizeof(disparam));
			if (ioctl(runtime_state.kdvm_fd, KDDISPTYPE, &disparam) == 0)
				adapter_type = (int)disparam.type;
		}
		runtime_state.mode = choose_default_mode(adapter_type);
	}

	if (!runtime_state.mode) {
		fprintf(stderr, "wsdemo: no supported graphics mode was found; this demo currently handles vga320x200, vdc640x400v, and vdc800x600e\n");
		cleanup_runtime();
		return 1;
	}

	if (install_signal_handlers() < 0) {
		fprintf(stderr, "wsdemo: unable to install signal handlers: %s\n", strerror(errno));
		cleanup_runtime();
		return 1;
	}

	if (set_vt_process_mode(runtime_state.vt_fd) < 0) {
		fprintf(stderr, "wsdemo: unable to take VT process ownership: %s\n", strerror(errno));
		cleanup_runtime();
		return 1;
	}

	if (enter_graphics_mode() < 0) {
		fprintf(stderr, "wsdemo: unable to enter graphics mode: %s\n", strerror(errno));
		cleanup_runtime();
		return 1;
	}

	print_mode_details(options.seconds);
	printf("wsdemo: move the mouse or press keys; press Esc or q to exit early\n");
	fflush(stdout);

	deadline = time(NULL) + options.seconds;
	while (!terminate_requested) {
		handle_vt_transitions();
		if (terminate_requested)
			break;
		if (time(NULL) >= deadline)
			break;
		if (!runtime_state.graphics_active) {
			usleep(20000);
			continue;
		}
		consume_queue_events();
		redraw_scene();
		usleep(16000);
	}

	cleanup_runtime();
	printf("wsdemo: keys=%u buttons=%u motion=%u last-key=0x%x cursor=(%d,%d) vt-release=%u vt-acquire=%u\n",
		runtime_state.key_events,
		runtime_state.button_events,
		runtime_state.motion_events,
		runtime_state.last_key_code,
		runtime_state.cursor_x,
		runtime_state.cursor_y,
		runtime_state.vt_releases,
		runtime_state.vt_acquires);
	return 0;
}