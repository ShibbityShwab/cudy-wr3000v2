// SPDX-License-Identifier: GPL-2.0
/*
 * luofu-wdt: watchdog driver for the Hi5671Y "luofu" SoC
 * (DT compatible "hisilicon,luofu-wdt"; the vendor binds "hsan,hsan-watchdog").
 *
 * WHERE THIS COMES FROM
 *
 * The vendor ships its watchdog as `hi_wdg.ko` and its DT node carries a vendor
 * binding (reg = <0x14880000 0x1000>, en-offset 0x64, set-offset 0x50,
 * clr-offset 0x70, int-status-offset 0x100, enable/stop/reset value pairs).
 * A full decompilation of hi_wdt_hw_enable / _hw_set_timeout / _hw_clear backed
 * every store below; the four defects that the lab copy carried (ping writing 0
 * instead of reset-val0/val1, the missing hwver-1/2 timeout paths, the absent
 * hwver read, and the wrong enable/disable order) are fixed here.
 *
 * TIMEOUT ENCODING, from hi_wdt_hw_set_timeout's three bfi paths:
 *
 *   hwver 0: clear mask 0xfffff007, field at bit 3,  value (secs - 1)
 *   hwver 1: clear mask 0xfff003ff, field at bit 10, value (2 * secs - 1)
 *   hwver 2: clear mask 0xfff803ff, field at bit 10, value (secs - 1)
 *
 * This board's DT says hwver = <2>, and the vendor's live set-offset reads
 * 0x30007400: bits[10:18] = 29, i.e. 30 s with the hwver-2 formula, which also
 * matches the vendor's own "timeout=30 sec" dmesg line.
 *
 * The one discipline kept from every other luofu driver: probe performs reads
 * only. A store is issued only from ->start/->stop/->ping/->set_timeout, i.e.
 * when userspace asks for the watchdog.
 */

#include <linux/delay.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/watchdog.h>

#define LUOFU_WDT_MASK_HWVER0	0xfffff007u
#define LUOFU_WDT_MASK_HWVER1	0xfff003ffu
#define LUOFU_WDT_MASK_HWVER2	0xfff803ffu
#define LUOFU_WDT_SHIFT_HWVER0	3
#define LUOFU_WDT_SHIFT_HWVER12	10

struct luofu_wdt {
	struct watchdog_device	wdd;
	struct device		*dev;
	void __iomem		*base;

	u32	en_offset;
	u32	set_offset;
	u32	clr_offset;
	u32	int_status_offset;

	u32	enable_val0;
	u32	enable_val1;
	u32	stop_val0;
	u32	stop_val1;
	u32	reset_val0;
	u32	reset_val1;

	u32	hwver;
};

static int luofu_wdt_start(struct watchdog_device *wdd)
{
	struct luofu_wdt *w = watchdog_get_drvdata(wdd);

	/* The vendor writes val1 then val0 on enable, val0 then val1 on stop. */
	writel(w->enable_val1, w->base + w->en_offset);
	writel(w->enable_val0, w->base + w->en_offset);
	return 0;
}

static int luofu_wdt_stop(struct watchdog_device *wdd)
{
	struct luofu_wdt *w = watchdog_get_drvdata(wdd);

	writel(w->stop_val0, w->base + w->en_offset);
	writel(w->stop_val1, w->base + w->en_offset);
	return 0;
}

static int luofu_wdt_ping(struct watchdog_device *wdd)
{
	struct luofu_wdt *w = watchdog_get_drvdata(wdd);

	/*
	 * hi_wdt_hw_clear writes reset-val0 then reset-val1 to clr-offset and
	 * leaves the register holding reset-val1, which is exactly what the
	 * live vendor reads at 0x14880070 (0xAA55A5A5). Writing 0 here is the
	 * old lab bug and does not clear the timer.
	 */
	writel(w->reset_val0, w->base + w->clr_offset);
	writel(w->reset_val1, w->base + w->clr_offset);
	return 0;
}

static int luofu_wdt_set_timeout(struct watchdog_device *wdd, unsigned int secs)
{
	struct luofu_wdt *w = watchdog_get_drvdata(wdd);
	u32 mask, shift, field, v;

	if (secs == 0 || secs > wdd->max_timeout)
		return -EINVAL;

	switch (w->hwver) {
	case 0:
		mask = LUOFU_WDT_MASK_HWVER0;
		shift = LUOFU_WDT_SHIFT_HWVER0;
		field = secs - 1;
		break;
	case 1:
		mask = LUOFU_WDT_MASK_HWVER1;
		shift = LUOFU_WDT_SHIFT_HWVER12;
		field = 2 * secs - 1;
		break;
	default:
		mask = LUOFU_WDT_MASK_HWVER2;
		shift = LUOFU_WDT_SHIFT_HWVER12;
		field = secs - 1;
		break;
	}

	v = readl(w->base + w->set_offset);
	v = (v & mask) | (field << shift);
	writel(v, w->base + w->set_offset);

	wdd->timeout = secs;
	return 0;
}

static const struct watchdog_info luofu_wdt_info = {
	.options	= WDIOF_SETTIMEOUT | WDIOF_KEEPALIVEPING | WDIOF_MAGICCLOSE,
	.identity	= "luofu-wdt",
};

static const struct watchdog_ops luofu_wdt_ops = {
	.owner		= THIS_MODULE,
	.start		= luofu_wdt_start,
	.stop		= luofu_wdt_stop,
	.ping		= luofu_wdt_ping,
	.set_timeout	= luofu_wdt_set_timeout,
};

static int luofu_wdt_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct luofu_wdt *w;
	int ret;

	w = devm_kzalloc(dev, sizeof(*w), GFP_KERNEL);
	if (!w)
		return -ENOMEM;

	w->dev = dev;
	/*
	 * devm_platform_ioremap_resource() claims the whole 0x14880000 page as a
	 * resource, and the crg driver (clocks + reset controller) lives on the
	 * same page, so the request failed with -EBUSY and this probe never
	 * registered the device. Plain devm_ioremap() maps without claiming.
	 */
	{
		struct resource *res = platform_get_resource(pdev, IORESOURCE_MEM, 0);

		if (!res)
			return -ENODEV;
		w->base = devm_ioremap(dev, res->start, resource_size(res));
		if (!w->base)
			return -ENOMEM;
	}

	/* every value comes from the vendor's own DT node */
	ret = of_property_read_u32(dev->of_node, "en-offset", &w->en_offset);
	if (ret)
		return dev_err_probe(dev, ret, "missing en-offset\n");
	ret = of_property_read_u32(dev->of_node, "set-offset", &w->set_offset);
	if (ret)
		return dev_err_probe(dev, ret, "missing set-offset\n");
	ret = of_property_read_u32(dev->of_node, "clr-offset", &w->clr_offset);
	if (ret)
		return dev_err_probe(dev, ret, "missing clr-offset\n");

	of_property_read_u32(dev->of_node, "int-status-offset",
			     &w->int_status_offset);
	of_property_read_u32(dev->of_node, "enable-val0", &w->enable_val0);
	of_property_read_u32(dev->of_node, "enable-val1", &w->enable_val1);
	of_property_read_u32(dev->of_node, "stop-val0", &w->stop_val0);
	of_property_read_u32(dev->of_node, "stop-val1", &w->stop_val1);
	of_property_read_u32(dev->of_node, "reset-val0", &w->reset_val0);
	of_property_read_u32(dev->of_node, "reset-val1", &w->reset_val1);
	if (of_property_read_u32(dev->of_node, "hwver", &w->hwver))
		w->hwver = 2;	/* this board's DT value; the live register agrees */

	w->wdd.info = &luofu_wdt_info;
	w->wdd.ops = &luofu_wdt_ops;
	w->wdd.parent = dev;

	watchdog_init_timeout(&w->wdd, 0, dev);
	w->wdd.min_timeout = 1;
	w->wdd.max_timeout = 0x200;

	watchdog_set_drvdata(&w->wdd, w);
	watchdog_stop_on_reboot(&w->wdd);
	watchdog_stop_on_unregister(&w->wdd);

	ret = devm_watchdog_register_device(dev, &w->wdd);
	if (ret)
		return ret;

	dev_info(dev,
		 "luofu-wdt: registered (hwver %u, en+0x%x set+0x%x clr+0x%x), timeout %us, max %us\n",
		 w->hwver, w->en_offset, w->set_offset, w->clr_offset,
		 w->wdd.timeout, w->wdd.max_timeout);
	return 0;
}

static const struct of_device_id luofu_wdt_of_match[] = {
	{ .compatible = "hisilicon,luofu-wdt" },
	{ .compatible = "hsan,hsan-watchdog" },
	{ }
};
MODULE_DEVICE_TABLE(of, luofu_wdt_of_match);

static struct platform_driver luofu_wdt_driver = {
	.probe	= luofu_wdt_probe,
	.driver	= {
		.name		= "luofu-wdt",
		.of_match_table	= luofu_wdt_of_match,
	},
};
module_platform_driver(luofu_wdt_driver);

MODULE_DESCRIPTION("Hi5671Y luofu watchdog driver");
MODULE_LICENSE("GPL v2");
