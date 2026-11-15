// SPDX-License-Identifier: GPL-2.0
/*
 * luofu-phy: the Hisilicon "Genius" PHY behind the luofu internal switch.
 *
 * The vendor's hi_kphy.ko registers a C22 PHY driver whose match table is
 * phy_id 0x20669a00 with mask 0xffffff00 (read out of the module's .data at +0x50), and its own
 * messages show why the PHYs are not standard parts:
 *
 *     [GEPHY]Genius Phy hwVer:0x%x fwVer:0x%x
 *     lsw/hi_ephy_%xv%x.bin        <- a firmware patch file loaded from the rootfs
 *
 * The vendor's driver downloads that patch into the PHY before the link comes up. Our clean-room
 * driver deliberately starts with the genphy operations only: the C22 registers (BMSR/BMCR/ANAR
 * etc.) are standard, so link, autonegotiation and speed should work without the patch, and the
 * patch download becomes an optimisation we can reverse later from the same disassembly.
 *
 * The patch load is therefore a known TODO, not a hidden failure: if the link trains but the PHY
 * reports odd values, or the vendor's driver and ours disagree on the link state, that is the
 * missing patch, and the next step is to decode hi_ephy_*.bin's format from hi_kphy.ko.
 */

#include <linux/module.h>
#include <linux/phy.h>

#define LUOFU_GENIUS_PHY_ID	0x20669a00
#define LUOFU_GENIUS_PHY_MASK	0xffffff00

static struct phy_driver luofu_genius_driver[] = {
	{
		.phy_id		= LUOFU_GENIUS_PHY_ID,
		.phy_id_mask	= LUOFU_GENIUS_PHY_MASK,
		.name		= "Luofu Genius PHY",
		.features	= PHY_GBIT_FEATURES,
		.config_aneg	= genphy_config_aneg,
		.read_status	= genphy_read_status,
		.suspend	= genphy_suspend,
		.resume		= genphy_resume,
	},
};

module_phy_driver(luofu_genius_driver);

MODULE_DESCRIPTION("HiSilicon luofu Genius PHY");
MODULE_LICENSE("GPL v2");
