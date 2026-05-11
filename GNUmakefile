ARCH ?= i686
JINX ?= $(realpath jinx)
BUILD_FOLDER ?= $(realpath ../svr4-build)
SYSROOT = $(BUILD_FOLDER)/sysroot
HDD_IMAGE = $(BUILD_FOLDER)/hdd.img
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

BASE_PKGS=svr4_init bash coreutils
.PHONY: ensure-installed
ensure-installed:
	@cd $(BUILD_FOLDER) && $(JINX) install -f $(SYSROOT) $(BASE_PKGS)

.PHONY: hdd
hdd $(HDD_IMAGE): $(BUILD_FOLDER)/.jinx-parameters $(SYSROOT)/stand/unix $(SYSROOT)/usr/lib/libc.so ensure-installed
	$(PYTHON) tasks/make_image.py \
		--image $(HDD_IMAGE) \
		--sysroot $(SYSROOT)

.PHONY: qemu
qemu: $(HDD_IMAGE)
	qemu-system-i386 -drive format=raw,file=$(HDD_IMAGE) -net none -boot c -m 128 -debugcon stdio
