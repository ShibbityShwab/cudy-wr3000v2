// SPDX-License-Identifier: GPL-2.0
/*
 * luofu-crg - the clock gate and reset provider for the WR3000 v2 (HiSilicon
 * "luofu", SoC control page at 0x14880000).
 *
 * The DTS already describes this controller (compatible "hsan,crg", 16
 * "hsan,clk-gate" children whose ORDER is the LUOFU_CLK_* index table, one
 * #clock-cells for the gate id, two #reset-cells (offset, bit)), and the mach
 * code looks for a driver literally named "luofu-crg". The driver itself was
 * lost with the gmac/mdio sources, so every consumer that asks for a clock
 * (four GEMAC nodes, the MDIO bus, the FMC's sfc_clk) has been sitting in
 * -EPROBE_DEFER: the FMC does not require its clock so the flash still worked,
 * but the MACs refused to probe, which is why the vendor userspace on our
 * kernel saw only `lo`.
 *
 * One platform driver registers both providers from the one node:
 *  - one gate clock per child, parented on apb_clk, published with
 *    of_clk_add_hw_provider and indexed by child order;
 *  - a reset controller whose two-cell specifier (offset, bit) is folded into
 *    a single id, so assert/deassert become a bit write at base + offset.
 */
#include <linux/clk-provider.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_device.h>
#include <linux/platform_device.h>
#include <linux/reset-controller.h>
#include <linux/slab.h>
#include <linux/spinlock.h>

struct luofu_crg {
	void __iomem			*base;
	struct clk_hw_onecell_data	*clk_data;
	struct reset_controller_dev	rcdev;
	spinlock_t			lock;
};

static int luofu_crg_reset_xlate(struct reset_controller_dev *rcdev,
				 const struct of_phandle_args *spec)
{
	if (spec->args_count < 2)
		return -EINVAL;
	if (spec->args[0] > 0xff || spec->args[1] > 0x1f)
		return -EINVAL;

	return (spec->args[0] << 8) | spec->args[1];
}

static int luofu_crg_reset_set(struct reset_controller_dev *rcdev,
			       unsigned long id, bool assert)
{
	struct luofu_crg *crg = container_of(rcdev, struct luofu_crg, rcdev);
	void __iomem *reg = crg->base + (id >> 8);
	u32 bit = BIT(id & 0xff);
	unsigned long flags;
	u32 v;

	spin_lock_irqsave(&crg->lock, flags);
	v = readl(reg);
	if (assert)
		v |= bit;
	else
		v &= ~bit;
	writel(v, reg);
	spin_unlock_irqrestore(&crg->lock, flags);

	return 0;
}

static int luofu_crg_reset_assert(struct reset_controller_dev *rcdev,
				  unsigned long id)
{
	return luofu_crg_reset_set(rcdev, id, true);
}

static int luofu_crg_reset_deassert(struct reset_controller_dev *rcdev,
				    unsigned long id)
{
	return luofu_crg_reset_set(rcdev, id, false);
}

static int luofu_crg_reset_status(struct reset_controller_dev *rcdev,
				  unsigned long id)
{
	struct luofu_crg *crg = container_of(rcdev, struct luofu_crg, rcdev);

	return !!(readl(crg->base + (id >> 8)) & BIT(id & 0xff));
}

static int luofu_crg_reset(struct reset_controller_dev *rcdev,
			   unsigned long id)
{
	int ret = luofu_crg_reset_assert(rcdev, id);

	if (ret)
		return ret;
	return luofu_crg_reset_deassert(rcdev, id);
}

static const struct reset_control_ops luofu_crg_reset_ops = {
	.assert		= luofu_crg_reset_assert,
	.deassert	= luofu_crg_reset_deassert,
	.status		= luofu_crg_reset_status,
	.reset		= luofu_crg_reset,
};

static int luofu_crg_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct device_node *np = dev->of_node, *child;
	struct luofu_crg *crg;
	struct clk_hw **hws;
	int ngates = 0, i = 0, ret;

	crg = devm_kzalloc(dev, sizeof(*crg), GFP_KERNEL);
	if (!crg)
		return -ENOMEM;

	crg->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(crg->base))
		return PTR_ERR(crg->base);

	spin_lock_init(&crg->lock);

	for_each_child_of_node(np, child)
		if (of_device_is_compatible(child, "hsan,clk-gate"))
			ngates++;
	if (!ngates)
		return -ENODEV;

	crg->clk_data = devm_kzalloc(dev,
				     struct_size(crg->clk_data, hws, ngates),
				     GFP_KERNEL);
	if (!crg->clk_data)
		return -ENOMEM;
	crg->clk_data->num = ngates;
	hws = crg->clk_data->hws;

	for_each_child_of_node(np, child) {
		const char *name = NULL;
		u32 off, bit;

		if (!of_device_is_compatible(child, "hsan,clk-gate"))
			continue;

		if (of_property_read_u32(child, "reg-offset", &off) ||
		    of_property_read_u32(child, "bit", &bit)) {
			dev_warn(dev, "%pOF: no reg-offset/bit\n", child);
			i++;
			continue;
		}

		of_property_read_string(child, "clock-output-names", &name);

		hws[i] = clk_hw_register_gate(dev, name, "apb_clk", 0,
					      crg->base + off, bit, 0,
					      &crg->lock);
		if (IS_ERR(hws[i])) {
			dev_warn(dev, "%pOF: gate %u failed: %ld\n", child, i,
				 PTR_ERR(hws[i]));
			hws[i] = NULL;
		}
		i++;
	}

	ret = devm_of_clk_add_hw_provider(dev, of_clk_hw_onecell_get,
					  crg->clk_data);
	if (ret)
		return ret;

	crg->rcdev.owner = THIS_MODULE;
	crg->rcdev.nr_resets = 0x10000;
	crg->rcdev.ops = &luofu_crg_reset_ops;
	crg->rcdev.of_node = np;
	crg->rcdev.of_xlate = luofu_crg_reset_xlate;

	ret = devm_reset_controller_register(dev, &crg->rcdev);
	if (ret)
		return ret;

	dev_info(dev, "luofu-crg: %d gate clocks and the reset controller registered\n",
		 ngates);

	return 0;
}

static const struct of_device_id luofu_crg_of_match[] = {
	{ .compatible = "hsan,crg" },
	{ }
};

static struct platform_driver luofu_crg_driver = {
	.probe	= luofu_crg_probe,
	.driver	= {
		.name		= "luofu-crg",
		.of_match_table	= luofu_crg_of_match,
	},
};
builtin_platform_driver(luofu_crg_driver);
