/* devmem - tiny static /dev/mem 32-bit reader/writer for the luofu bench image
 *
 * usage: devmem ADDRESS [WIDTH [VALUE]]
 *   devmem 0x10100c08            read 32-bit word
 *   devmem 0x124000d8 32 0x800   write 32-bit word
 *
 * Built for the OpenWrt 6.18 bench image so register experiments can run over
 * SSH without rebuilding the kernel.  The kernel needs CONFIG_DEVMEM=y and
 * STRICT_DEVMEM off for the MMIO windows to be mappable.
 */
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

int main(int argc, char **argv)
{
	unsigned long target, offset;
	unsigned int width = 32;
	uint32_t value = 0, *map;
	int fd, has_value = 0, write_op = 0;

	if (argc < 2) {
		fprintf(stderr, "usage: %s ADDRESS [WIDTH [VALUE]]\n", argv[0]);
		return 2;
	}
	target = strtoul(argv[1], NULL, 0);
	if (argc >= 3) {
		width = (unsigned int)strtoul(argv[2], NULL, 0);
		if (width != 32) {
			fprintf(stderr, "only 32-bit access is supported\n");
			return 2;
		}
	}
	if (argc >= 4) {
		value = (uint32_t)strtoul(argv[3], NULL, 0);
		has_value = 1;
		write_op = 1;
	}

	fd = open("/dev/mem", (write_op ? (O_RDWR | O_SYNC) : (O_RDONLY | O_SYNC)));
	if (fd < 0) {
		perror("open /dev/mem");
		return 1;
	}
	offset = target & ~(unsigned long)(getpagesize() - 1);
	map = mmap(NULL, getpagesize(), write_op ? (PROT_READ | PROT_WRITE) : PROT_READ,
		   MAP_SHARED, fd, (off_t)offset);
	if (map == MAP_FAILED) {
		perror("mmap");
		close(fd);
		return 1;
	}
	map += (target - offset) / 4;

	if (has_value) {
		*map = value;
		printf("wrote 0x%08x at 0x%08lx (read back 0x%08x)\n", value, target, *map);
	} else {
		printf("0x%08x\n", *map);
	}
	munmap(map, getpagesize());
	close(fd);
	return 0;
}
