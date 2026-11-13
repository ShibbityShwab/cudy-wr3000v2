/* SPDX-License-Identifier: GPL-2.0 */
#ifndef _ASM_VERMAGIC_H
#define _ASM_VERMAGIC_H

#include <linux/stringify.h>

/*
 * Add the ARM architecture version to the version magic string
 */
#define MODULE_ARCH_VERMAGIC_ARMVSN "ARMv" __stringify(__LINUX_ARM_ARCH__) " "

/* Add __virt_to_phys patching state as well */
/*
 * LAB CHOICE (2026-11-13): the vendor's own modules (their whole hi_* driver
 * stack, including the network and wireless drivers) were built against a
 * kernel configured without phys-to-virt patching, so their vermagic reads
 * "ARMv7 " and this kernel's reads "ARMv7 p2v8 ". ARCH_MULTIPLATFORM selects
 * the option, so it cannot simply be turned off in our config. Emitting the
 * same tag lets the vendor's modules load; the patching itself still happens
 * and the modules call the kernel's patched translation helpers.
 */
#define MODULE_ARCH_VERMAGIC_P2V ""

/* Add instruction set architecture tag to distinguish ARM/Thumb kernels */
#ifdef CONFIG_THUMB2_KERNEL
#define MODULE_ARCH_VERMAGIC_ARMTHUMB "thumb2 "
#else
#define MODULE_ARCH_VERMAGIC_ARMTHUMB ""
#endif

#define MODULE_ARCH_VERMAGIC \
	MODULE_ARCH_VERMAGIC_ARMVSN \
	MODULE_ARCH_VERMAGIC_ARMTHUMB \
	MODULE_ARCH_VERMAGIC_P2V

#endif /* _ASM_VERMAGIC_H */
