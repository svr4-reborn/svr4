ARCH ?= i686
JINX ?= $(realpath jinx)
BUILD_FOLDER ?= $(realpath ../svr4-build)
SYSROOT = $(BUILD_FOLDER)/sysroot
HDD_IMAGE = $(BUILD_FOLDER)/hdd.img
HDD_SIZE ?= 4096 # MiB
DISK_ADDRESSING ?= lba28
RAM_SIZE ?= 1024 # MiB
SWAP_SIZE ?= 128 # MiB
QEMU_DEBUG_LOG = $(BUILD_FOLDER)/qemu-debugcon.log
PYTHON ?= .venv/bin/python

$(BUILD_FOLDER)/.jinx-parameters:
	@cd $(BUILD_FOLDER) && $(JINX) init .. ARCH=$(ARCH)


.PHONY: build-uts
build-uts $(SYSROOT)/stand/unix: $(BUILD_FOLDER)/.jinx-parameters
	@cd $(BUILD_FOLDER) && $(JINX) build uts
	@cd $(BUILD_FOLDER) && $(JINX) install -f $(SYSROOT) uts

.PHONY: build-mlibc
build-mlibc $(SYSROOT)/usr/lib/libc.so: $(BUILD_FOLDER)/.jinx-parameters
	@cd $(BUILD_FOLDER) && $(JINX) build mlibc
	@cd $(BUILD_FOLDER) && $(JINX) install -f $(SYSROOT) mlibc

BASE_PKGS=base-files svr4_init svr4_iputils bash coreutils wsdiag wsdemo xorg-server xorg-twm xorg-drivers xorg-apps
THREADTEST_PKGS=svr4_threadtests
.PHONY: ensure-installed
ensure-installed:
	@cd $(BUILD_FOLDER) && $(JINX) install -f $(SYSROOT) $(BASE_PKGS)

.PHONY: build-threadtests
build-threadtests: $(BUILD_FOLDER)/.jinx-parameters $(SYSROOT)/usr/lib/libc.so
	@cd $(BUILD_FOLDER) && $(JINX) build $(THREADTEST_PKGS)
	@cd $(BUILD_FOLDER) && $(JINX) install -f $(SYSROOT) $(THREADTEST_PKGS)

.PHONY: hdd-threadtests
hdd-threadtests: build-threadtests hdd

.PHONY: hdd
hdd $(HDD_IMAGE): $(BUILD_FOLDER)/.jinx-parameters $(SYSROOT)/stand/unix $(SYSROOT)/usr/lib/libc.so ensure-installed
	$(PYTHON) tasks/make_image.py \
		--image $(HDD_IMAGE) \
		--sysroot $(SYSROOT) \
		--size $(HDD_SIZE) \
		--disk-addressing $(DISK_ADDRESSING) \
		--swap-size $(SWAP_SIZE) \

.PHONY: qemu
qemu: $(HDD_IMAGE) qemu-no-rebuild

.PHONY: qemu-no-rebuild
qemu-no-rebuild:
	qemu-system-i386 -machine pc,vmport=off -drive format=raw,file=$(HDD_IMAGE) -net none -boot c -m $(RAM_SIZE) -debugcon stdio -vga cirrus -display gtk,grab-on-hover=on

.PHONY: qemu-curses
qemu-curses: $(HDD_IMAGE)
	@echo "QEMU debug console output: $(QEMU_DEBUG_LOG)"
	qemu-system-i386 -machine pc,vmport=off -drive format=raw,file=$(HDD_IMAGE) -net none -boot c -m $(RAM_SIZE) -display curses -debugcon file:$(QEMU_DEBUG_LOG)
