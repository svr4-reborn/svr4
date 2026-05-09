ARCH ?= i686
BUILD_FOLDER ?= build
SYSROOT = $(BUILD_FOLDER)/sysroot
HDD_IMAGE = $(BUILD_FOLDER)/hdd.img

$(BUILD_FOLDER)/.jinx-parameters:
	@cd $(BUILD_FOLDER) && ../jinx init .. ARCH=$(ARCH)


.PHONY: build-uts
build-uts $(SYSROOT)/stand/unix: $(BUILD_FOLDER)/.jinx-parameters
	@cd $(BUILD_FOLDER) && ../jinx build uts
	@cd $(BUILD_FOLDER) && ../jinx install -f sysroot uts

.PHONY: build-mlibc
build-mlibc $(SYSROOT)/usr/lib/libc.so: $(BUILD_FOLDER)/.jinx-parameters
	@cd $(BUILD_FOLDER) && ../jinx build mlibc
	@cd $(BUILD_FOLDER) && ../jinx install -f sysroot mlibc

.PHONY: hdd
hdd $(HDD_IMAGE): $(BUILD_FOLDER)/.jinx-parameters $(SYSROOT)/stand/unix $(SYSROOT)/usr/lib/libc.so
	source .venv/bin/activate && python3 tasks/make_image.py \
		--image $(HDD_IMAGE) \
		--sysroot $(SYSROOT)

.PHONY: qemu
qemu: $(HDD_IMAGE)
	qemu-system-i386 -drive format=raw,file=$(HDD_IMAGE) -net none -boot c -m 64
