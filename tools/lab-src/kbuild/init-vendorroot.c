static inline long sc1(long n, long a)
{
    register long r0 asm("r0") = a; register long r7 asm("r7") = n;
    asm volatile("svc #0" : "+r"(r0) : "r"(r7) : "memory"); return r0;
}
static inline long sc0(long n)
{
    register long r0 asm("r0") = 0; register long r7 asm("r7") = n;
    asm volatile("svc #0" : "+r"(r0) : "r"(r7) : "memory"); return r0;
}
static inline long sc2(long n, long a, long b)
{
    register long r0 asm("r0") = a; register long r1 asm("r1") = b; register long r7 asm("r7") = n;
    asm volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r7) : "memory"); return r0;
}
static inline long sc3(long n, long a, long b, long c)
{
    register long r0 asm("r0") = a; register long r1 asm("r1") = b; register long r2 asm("r2") = c; register long r7 asm("r7") = n;
    asm volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r7) : "memory"); return r0;
}
static inline long sc5(long n, long a, long b, long c, long d, long e)
{
    register long r0 asm("r0") = a; register long r1 asm("r1") = b; register long r2 asm("r2") = c; register long r3 asm("r3") = d; register long r4 asm("r4") = e; register long r7 asm("r7") = n;
    asm volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r7) : "memory"); return r0;
}
static inline long sc6(long n, long a, long b, long c, long d, long e, long f)
{
    register long r0 asm("r0") = a; register long r1 asm("r1") = b; register long r2 asm("r2") = c;
    register long r3 asm("r3") = d; register long r4 asm("r4") = e; register long r5 asm("r5") = f;
    register long r7 asm("r7") = n;
    asm volatile("svc #0" : "+r"(r0) : "r"(r1), "r"(r2), "r"(r3), "r"(r4), "r"(r5), "r"(r7) : "memory");
    return r0;
}

#define SYS_exit     1
#define SYS_fork     2
#define SYS_sync     36
#define SYS_write    4
#define SYS_open     5
#define SYS_chmod    15
#define SYS_mount    21
#define SYS_close    6
#define SYS_chdir    12
#define SYS_finit_module 379
#define SYS_umount2  52
#define SYS_execve   11
#define SYS_mkdir    39
#define SYS_mknod    14
#define SYS_pivot    218
#define SYS_chroot   61
#define SYS_lseek    19
#define SYS_mmap2    192
#define SYS_nanosleep 162

#define MS_RDONLY    1
#define MS_MOVE      8192

static const char p_new[]   = "/newroot";
static const char p_root[]  = "/";
static const char p_wdt[]   = "/dev/watchdog";
static const char p_dot[]   = ".";
static const char p_init[]  = "/sbin/init";
static const char p_pre[]   = "/etc/preinit";
static const char p_path[]  = "PATH=/usr/sbin:/usr/bin:/sbin:/bin";
static const char p_home[]  = "HOME=/";
static const char p_term[]  = "TERM=linux";
static const char p_ubi[]   = "/dev/ubiblock0_0";
static const char p_mtd13[] = "/dev/mtdblock13";
/* NON-PERSISTENT TEST MASKS (2026-11-17): a no-op script in the initramfs (RAM, vanishes on
 * reboot) is bind-mounted over the vendor kmodloader/NFT script for THIS boot only. Stock
 * fallback boots see the untouched overlay. */
static const char p_noop[]  = "/omo-noop";
static const char p_kmod[]  = "/vendor/sbin/kmodloader";
static const char p_nft[]   = "/vendor/etc/rc.d/S99nft-qos";
static const char p_hsap[]  = "/vendor/etc/init.d/hsan_appm";
static const char p_wand[]  = "/vendor/sbin/wandetect";
static const char p_hot[]   = "/vendor/etc/hotplug.d/wandetect/08-wan-detect";
static const char sh_noop[] =
    "#!/bin/sh\n"
    "# OMO non-persistent mask: stock module loading/NFT is skipped on the lab kernel only.\n"
    "exit 0\n";

/*
 * THE VENDOR STACK, LOADED IN THE VENDOR'S OWN ORDER (2026-11-14).
 *
 * /etc/rc.d/luofu on the vendor image loads these in exactly this sequence, and the order is the
 * dependency graph: the LSW trio before the MDIO, the MDIO and PHY before the MAC, the kcfe chain
 * before hi_swa. The vendor's scripts only fail to do this on our kernel because their first insmod
 * is refused, so the chain never starts. The modules under /vendor/upper/lib/hisilicon/ko are the
 * patched copies (objcopy added the .plt sections the loader demands), and the overlay upper is
 * where they live until the pivot makes it /lib/hisilicon/ko.
 */
static const char *const vmods[] = {
    /*
     * ksecurec FIRST (2026-11-17): hi_basic imports memcpy_s/strcpy_s/vsnprintf_s and the rest
     * of the SafeC family, all exported by ksecurec.ko. Without it every later module dies on
     * unknown symbols, which is exactly what the 3dq boot showed.
     */
    "ksecurec",
    "hi_basic", "hi_kpinctrl", "hi_sysctrl", "hi_acp", "hi_kpie",
    /* v14: lab gmac/mdio/phy are back (U-Boot-safe DTS); the WAN rootif write is skipped by a
     * non-persistent initramfs bind-mount, so no vendor MAC driver is needed. */
    "hi_lsw_pub", "hi_lsw_dp", "hi_lsw_pfe",
    "hi_kcfe_pub", "hi_kcfe_lrn", "hi_kcfe_lrn_l3", "hi_kcfe_lrn_l4",
    "hi_kcfe_lrn_mc", "hi_kcfe_mc_list", "hi_kcfe_lrn_vxlan", "hi_kcara", "hi_khslink",
    "hi_swa",
    /*
     * NO hyfi-bridging PRELOAD (2026-11-17). RE verdict: hyfi_bridging is built against the
     * vendor's sk_buff ABI (data at 0x118 vs our 0xa0, +0x74/+0x78 struct delta), so its first
     * netlink receive reads skb->data out of bounds and oopses. It must not run until a sk_buff
     * ABI port is attempted; the vendor userspace tolerates its absence in the known-good stack.
     */
    0
};

static void append(const char *path, const char *s, long n)
{
    long fd = sc3(SYS_open, (long)path, 0x441, 0644);

    if (fd >= 0) {
        sc3(SYS_write, fd, (long)s, n);
        sc2(SYS_close, fd, 0);
    }
}

static void wfile(const char *path, const char *s, long mode);

static void bind_mask(const char *src, const char *target)
{
    sc5(SYS_mount, (long)src, (long)target, 0, 4096 /* MS_BIND */, 0);
}

static void write_test_masks(void)
{
    wfile((char *)p_noop, sh_noop, 0755);
    bind_mask(p_noop, p_kmod);
    bind_mask(p_noop, p_nft);
    /* WAN-rootif skip for the lab boot only (patched copies live in this initramfs) */
    bind_mask("/omo-hsan_appm", p_hsap);
    bind_mask("/omo-wandetect", p_wand);
    bind_mask("/omo-wan-detect", p_hot);
}

static int utoa(char *b, long v)
{
    char t[16];
    int i = 0, j = 0;

    if (v < 0) {
        b[j++] = '-';
        v = -v;
    }
    do {
        long q = 0, r = v;

        while (r >= 10) {
            r -= 10;
            q++;
        }
        t[i++] = '0' + r;
        v = q;
    } while (v);
    while (i)
        b[j++] = t[--i];
    return j;
}

static void load_vendor_modules(void)
{
    static const char pfx[] = "/vendor/upper/lib/hisilicon/ko/";
    char path[96];
    int i, j;

    for (i = 0; vmods[i]; i++) {
        const char *s = vmods[i];
        char line[64];
        int k = 0;
        long fd, ret = -1;

        for (j = 0; pfx[j] && j < 40; j++)
            path[j] = pfx[j];
        while (*s && j < 90)
            path[j++] = *s++;
        path[j++] = '.';
        path[j++] = 'k';
        path[j++] = 'o';
        path[j] = 0;

        fd = sc3(SYS_open, (long)path, 0, 0);
        if (fd >= 0) {
            ret = sc3(SYS_finit_module, fd, (long)"", 0);
            sc2(SYS_close, fd, 0);
        }

        /*
         * BOTH CHANNELS, ON PURPOSE (3dk, 2026-11-16).
         *
         * The file lands only when /vendor is writable, and the console capture is the
         * only readout that exists on a boot with no network. 3dh's capture proves the
         * stack loads and `eth2` comes up at 1Gbps, yet its mod-load.log was never read
         * back; a kmsg line per module makes the same verdict readable off the UART alone.
         */
        k = 0;
        line[k++] = '<';
        line[k++] = '6';
        line[k++] = '>';
        line[k++] = 'l';
        line[k++] = 'o';
        line[k++] = 'a';
        line[k++] = 'd';
        line[k++] = ' ';
        s = vmods[i];
        while (*s)
            line[k++] = *s++;
        line[k++] = ' ';
        line[k++] = 'f';
        line[k++] = 'd';
        line[k++] = '=';
        k += utoa(line + k, fd);
        line[k++] = ' ';
        line[k++] = 'r';
        line[k++] = 'e';
        line[k++] = 't';
        line[k++] = '=';
        k += utoa(line + k, ret);
        line[k++] = '\n';
        append("/dev/kmsg", line, k);
        append("/vendor/upper/mod-load.log", line + 3, k - 3);
    }
}
static const char p_sdev[]  = "/dev";
static const char p_ndev[]  = "/mnt/lower/dev";
static const char p_olay[]  = "/mnt/new";
static const char p_low[]   = "/mnt/lower";
static const char p_over[]  = "/overlay";
static const char p_sq[]    = "squashfs";
static const char p_vend[]  = "/vendor";
static const char p_vmtd[]  = "mtd:rootfs_data";
static const char p_vetc[]  = "/vendor/upper/etc";
static const char p_vrc[]   = "/vendor/upper/etc/rc.local";
static const char p_vrd[]   = "/vendor/upper/etc/rc.d";
static const char p_vid[]   = "/vendor/upper/etc/init.d";
static const char sh_boot[] =
    "#!/bin/sh\n"
    "echo \"S10boot $(date +%s) $(uname -v)\" >> /boot.log\n"
    "exec /etc/init.d/boot \"$@\"\n";
/*
 * The vendor's /etc/rc.d/luofu loads the modules the boot depends on - above all hi_kpinctrl, without
 * which the MDIO and Ethernet pins are never muxed and no PHY is ever visible. Our init's own load of
 * hi_kpinctrl fails (-ENOENT on an unresolved symbol), so that script is not optional. It also loads
 * hi_kmdio/hi_kphy/hi_kmac, which our own drivers own. This shadow runs the vendor's script with only
 * those three lines removed, so pinmux, IRQ affinity, sysctls and everything else stay intact.
 */
static const char sh_luofu[] =
    "#!/bin/sh\n"
    "sed -e '/hi_kphy\\.ko/d' -e '/hi_kmdio\\.ko/d' -e '/hi_kmac\\.ko/d' /rom/etc/rc.d/luofu > /tmp/luofu-f.sh\n"
    "sh /tmp/luofu-f.sh\n";
static const char sh_hyfi[] =
    "#!/bin/sh\n"
    "echo \"S18hyfibrd $(date +%s)\" >> /boot.log\n"
    "exec /etc/init.d/hyfibrd \"$@\"\n";
static const char sh_net[]  =
    "#!/bin/sh\n"
    "echo \"S20network $(date +%s)\" >> /boot.log\n"
    "exec /etc/init.d/network \"$@\"\n";
static const char sh_done[] =
    "#!/bin/sh\n"
    "echo \"S95done $(date +%s)\" >> /boot.log\n"
    /*
     * FLAT APPENDS, NO BRACE BLOCK (2026-11-13).
     *
     * phase3by reached this script - the S95done breadcrumb is in /boot.log - but nothing after it
     * ran: no dump section, no kernel-ran line. A brace-grouped redirect is all-or-nothing and gave
     * no way to see where it stopped. Every line below is its own append, so one failing command
     * cannot take the rest down, and the dump-start / dump-end markers bracket exactly how far the
     * script got.
     */
    "OUT=/overlay/upper/net-dump-final.txt\n"
    "echo \"=== dump-start $(date +%s) ===\" >> $OUT\n"
    "echo \"=== kernel ===\" >> $OUT\n"
    "cat /proc/version >> $OUT 2>&1\n"
    "uname -v >> $OUT 2>&1\n"
    "echo \"=== uptime ===\" >> $OUT\n"
    "cat /proc/uptime >> $OUT 2>&1\n"
    "echo \"=== ip link ===\" >> $OUT\n"
    "ip link >> $OUT 2>&1\n"
    "echo \"=== ip addr ===\" >> $OUT\n"
    "ip addr >> $OUT 2>&1\n"
    "echo \"=== iw dev ===\" >> $OUT\n"
    "iw dev >> $OUT 2>&1\n"
    "echo \"=== dmesg net ===\" >> $OUT\n"
    "dmesg | grep -iE 'gmac|luofu|mdio|phy|eth[0-9]|netdev' >> $OUT 2>&1\n"
    "echo \"=== modules ===\" >> $OUT\n"
    "lsmod >> $OUT 2>&1\n"
    "echo \"=== module log ===\" >> $OUT\n"
    "dmesg | grep -iE 'module|hi_|insmod|finit|PLT|symbol' >> $OUT 2>&1\n"    "echo \"=== cells ===\" >> $OUT\n"
    "/sbin/devmem 0x10100C94 32 >> $OUT 2>&1\n"
    "/sbin/devmem 0x10100C98 32 >> $OUT 2>&1\n"
    "/sbin/devmem 0x10100C80 32 >> $OUT 2>&1\n"
    "/sbin/devmem 0x10100C18 32 >> $OUT 2>&1\n"
    "echo \"=== mdio regs ===\" >> $OUT\n"
    "/sbin/devmem 0x14000000 32 >> $OUT 2>&1\n"
    "/sbin/devmem 0x14000060 32 >> $OUT 2>&1\n"
    "/sbin/devmem 0x1400006C 32 >> $OUT 2>&1\n"
    "echo \"=== dump-end $(date +%s) ===\" >> $OUT\n"
    "echo \"$(date +%s) $(uname -v) shadow\" >> /overlay/upper/kernel-ran-final.log\n"
    "sync\n"
    "exec /etc/init.d/done \"$@\"\n"
    ;

static const char p_jf[]    = "jffs2";
static const char p_mem[]   = "/dev/mem";
static const char p_dtmp[]  = "devtmpfs";
static const char p_pst[]   = "/pstore";
static const char ps_ok[]   = "pstore mount OK: a backend registered\n";
static const char ps_no[]   = "pstore mount FAILED: no backend registered\n";
static const char marker[]  =
    "#!/bin/sh\n"
    "echo LUFU-PROCD > /etc/procd-ran\n"
    "KV=\"$(uname -v)\"\n"
    "echo \"$(date +%s) $KV\" >> /kernel-ran.log\n"
    "{\n"
    "echo \"=== $KV ===\"\n"
    "echo '== cells =='; /sbin/devmem 0x10100C8C 32; /sbin/devmem 0x10100C94 32\n"
    "cat /proc/version; uname -a\n"
    "echo '== net =='; ip addr 2>&1; ip link 2>&1\n"
    "echo '== dev =='; cat /proc/net/dev\n"
    "echo '== class =='; ls /sys/class/net\n"
    "echo '== mtd =='; cat /proc/mtd\n"
    "echo '== iw =='; iw phy 2>&1 | head -5; iw dev 2>&1 | head -5\n"
    "echo '== lsmod =='; lsmod 2>&1 | head -10\n"
    "echo '== dmesg =='; dmesg | grep -iE 'gmac|eth|mdio|phy|luofu|crg' | head -40\n"
    "} >> /net-state.log 2>&1\n"
    "sync\n"
    "case \"$KV\" in\n"
    "  *2023*) /sbin/devmem 0x10100C94 32 0xC0DE600E ;;\n"
    "  *)      /sbin/devmem 0x10100C94 32 0xC0DE600D ;;\n"
    "esac\n"
    "/usr/sbin/dropbear -p 22 -R\n";
static char *const argv[] = { (char *)p_init, 0 };
static char *const envp[] = { (char *)p_path, (char *)p_home, (char *)p_term, 0 };
static char *const argv_sh[] = { (char *)p_pre, 0 };

static void cell(unsigned long v);

/*
 * wfile() VERDICT CELL (3df, 2026-11-15).
 *
 * Every earlier instrument died silently. tag() is a no-op (line 372) and cell()
 * is never called (279/329), so C94 never carries anything; C18 is never written
 * by this init (only read, line 236) and the FMC's 5 s tick rewrites it
 * (drivers/mtd/nand/luofu/luofu-fmc.c:5197); C1C is the FMC's tick payload; C9C
 * is the mach's FMC diagnostic (arch/arm/mach-luofu/luofu.c:532).
 *
 * C98 is the FMC's NAND read-progress cell: written only from the read paths
 * during probe (luofu-fmc.c:905,1172,1197,1224,1257,1293,1331,1340,1343,1631),
 * all before /init runs and never from the 5 s tick, so a write from here is the
 * last writer and holds until the next boot. The cost is the FMC's last read
 * crumb for that boot, which read 0 on 3de anyway (mem-entries 13:33).
 *
 * One accumulated word, because only the last value survives:
 *   bits 31..24  record index
 *                  0  devtmpfs mounted on /dev            (3df prerequisite)
 *                  1  /vendor mount or remount verdict
 *                  2..8 the seven wfile() calls, source order
 *   bits 23..0   verdict, two's complement: >0 = the fd, <0 = -errno
 * The FIRST negative verdict is sticky, so a later success cannot erase the
 * one failure that matters.
 */
static long wrec_bad, wrec_bad_i;

static void wmark(long rec, long verdict)
{
    static long *wm;
    long fd, p;

    if (verdict < 0 && !wrec_bad) {
        wrec_bad = verdict;
        wrec_bad_i = rec;
    }
    if (wrec_bad) {
        rec = wrec_bad_i;
        verdict = wrec_bad;
    }
    if (wm == 0) {
        fd = sc2(SYS_open, (long)p_mem, 2 | 0x1000 /* O_RDWR|O_SYNC */);
        if (fd < 0) {
            sc3(SYS_mknod, (long)p_mem, 020600, 0x101);
            fd = sc2(SYS_open, (long)p_mem, 2 | 0x1000);
        }
        if (fd < 0)
            return;
        p = sc6(SYS_mmap2, 0L, 4096L, 3L, 1L, fd, 0x10100L);
        if ((unsigned long)p >= 0xfffff001UL)
            return;
        sc2(SYS_close, fd, 0);
        wm = (long *)p;
    }
    wm[0xC98 / 4] = ((rec & 0xff) << 24) | ((unsigned long)verdict & 0xffffffUL);
}

static void wfile(const char *path, const char *s, long mode)
{
    static long wf_n;
    long fd = sc3(SYS_open, (long)path, 0x241 /* WRONLY|CREAT|TRUNC */, mode);
    long n = 0;
    char line[96];
    char vl[128];
    int k = 0, m = 0;
    const char *p = path;

    /* THE CELL COMES FIRST: everything below needs a working /dev or a
     * writable /vendor, and those are exactly what this fire is testing. */
    wmark(2 + wf_n++, fd);

    line[k++] = '<';
    line[k++] = '6';
    line[k++] = '>';
    while (*p && k < 80)
        line[k++] = *p++;
    line[k++] = ' ';
    if (fd < 0) {
        line[k++] = 'E';
        line[k++] = '=';
        k += utoa(line + k, -fd);
    } else {
        line[k++] = 'O';
        line[k++] = 'K';
    }
    line[k++] = '\n';
    append("/dev/kmsg", line, k);

    /* SECOND CHANNEL, deliberately redundant: this lands only when the jffs2
     * mount is really writable, so a cell verdict with no wfile.log line is
     * exactly the read-only split. */
    p = path;
    while (*p && m < 88)
        vl[m++] = *p++;
    vl[m++] = ' ';
    vl[m++] = 'n';
    vl[m++] = '=';
    m += utoa(vl + m, wf_n - 1);
    vl[m++] = ' ';
    vl[m++] = 'f';
    vl[m++] = 'd';
    vl[m++] = '=';
    m += utoa(vl + m, fd);
    vl[m++] = '\n';
    append("/vendor/upper/wfile.log", vl, m);

    if (fd < 0)
        return;
    while (s[n])
        n++;
    sc3(SYS_write, fd, (long)s, n);
    sc2(SYS_close, fd, 0);
}

static void fail(long code)
{
    sc1(SYS_exit, 0xE0 + code);
    for (;;) { }
}

static void _start_unused(void);

/*
 * Step marker. The freestanding init has no console (the WR3000 v2 UART cannot
 * stop U-Boot and no console is wired in the lab), so every stage reports into
 * the SoC control cell at 0x10100C94 through /dev/mem. C94 survives a warm
 * reset and the vendor's own boot never writes it, so the value read after the
 * vendor returns names the exact stage this init reached.
 */
static void cell(unsigned long v)
{
    static long *mapped;
    long fd, p;

    if (!mapped) {
        fd = sc2(SYS_open, (long)p_mem, 2 | 0x1000 /* O_RDWR|O_SYNC */);
        if (fd < 0) {
            /*
             * devtmpfs has no /dev/mem node: the mem driver registers a plain
             * chrdev and never device_add()s one, so the initramfs /dev is
             * missing it until mdev runs. Create chr 1:1 ourselves.
             */
            sc3(SYS_mknod, (long)p_mem, 020600, 0x101);
            fd = sc2(SYS_open, (long)p_mem, 2 | 0x1000);
        }
        if (fd < 0)
            return;
        p = sc6(SYS_mmap2, 0L, 4096L, 3L, 1L, fd, 0x10100L);
        if ((unsigned long)p >= 0xfffff001UL)
            return;
        sc2(SYS_close, fd, 0);
        mapped = (long *)p;
    }
    mapped[0xC94 / 4] = (long)v;
}

static unsigned long tg;

/*
 * One accumulated word instead of one tag per stage: only the LAST value of C94
 * survives, so every stage ORs its own nibble and rewrites the whole word.
 * C94 = 0x6B000000 | tags:
 *   bit 0      the init runs
 *   bits 4-7   vendor-fs mount errno      (0 = mounted)
 *   bit 8      the shadow file was written
 *   bits 12-15 the /dev move errno
 *   bits 16-19 chdir(/mnt/lower) errno
 *   bits 20-23 pivot_root(".",".") errno
 *   bits 24-27 chroot(".") errno, only when the pivot was refused
 *   bit 28     execve attempted
 * fail() deliberately writes nothing: the accumulated word IS the report.
 */
static void tag(void)
{
    /*
     * DELIBERATELY A NO-OP (2026-11-13).
     *
     * This wrote the boot tag into C94, the one SYSCTRL cell on this board proven to accept a written
     * value. The gmac driver writes its probe crumbs to that same cell and its probes run first, so
     * every tag here was erasing the driver's evidence before the dump could read it. The dump's
     * kernel-ran-final.log line already proves the init ran and names the kernel, so the tag buys
     * nothing and C94 now belongs to the gmac crumbs.
     */
}

/*
 * USERSLACE WATCHDOG KEEPER (2026-11-13).
 *
 * The hsan watchdog is armed by u-boot with a 30 s timeout, and the vendor's
 * procd only opens /dev/watchdog once it is well into its own boot. On our
 * kernel every configuration so far dies before that hand-off completes. The
 * luofu-wdt driver is registered, so the misc device exists; this child holds it
 * open and writes the keepalive every 5 s for the rest of the box's life,
 * independent of anything the vendor's userspace does. It must be forked AFTER
 * the pivot so /dev is the moved devtmpfs.
 */
static void start_petter(void)
{
    long pid, fd;

    pid = sc0(SYS_fork);
    if (pid != 0)
        return;

    sc3(SYS_mknod, (long)p_wdt, 020600, (10 << 8) | 130);
    fd = sc3(SYS_open, (long)p_wdt, 1, 0);
    for (;;) {
        /* Retry the open every beat: the watchdog driver registers a few seconds into boot, and a
         * one-shot open that fails leaves the armed timer unfed - measured as a reset five seconds
         * into the vendor's first boot script. */
        if (fd < 0)
            fd = sc3(SYS_open, (long)p_wdt, 1, 0);
        if (fd >= 0)
            sc3(SYS_write, fd, (long)"1", 1);
        {
            long ts[2];
            ts[0] = 5;
            ts[1] = 0;
            sc2(SYS_nanosleep, (long)ts, 0);
        }
    }
}

void _start(void)
{
    long r, r2;
    long fd;

    /*
     * THE KEEPER STARTS FIRST (2026-11-14).
     *
     * U-Boot arms the watchdog before this kernel even starts, so every second before the keeper's
     * first ping comes straight off the margin. This used to fork just before the exec, after the
     * slow overlay mount; now the child exists before any mount runs and pings the whole time. The
     * /dev/watchdog node is the kernel's devtmpfs and the fd survives the pivot.
     */
    /*
     * /dev DOES NOT EXIST IN THIS INITRAMFS (3df, 2026-11-15).
     *
     * initramfs-site.cpio carries only `init`, and the kernel mounts devtmpfs on
     * /dev only from prepare_namespace() (init/do_mounts.c:630), which
     * init/main.c:1567-1570 skips whenever /init exists. So every /dev path in
     * this file has been an ENOENT on every boot: append("/dev/kmsg"), cell()'s
     * /dev/mem, and the keeper's /dev/watchdog. Create /dev and mount devtmpfs
     * here, before the keeper forks, and the keeper can finally feed the timer.
     */
    sc2(SYS_mkdir, (long)p_sdev, 0755);
    r = sc5(SYS_mount, (long)p_dtmp, (long)p_sdev, (long)p_dtmp, 0, 0);
    wmark(0, r);

    start_petter();

    tg = 1;
    tag();

    sc2(SYS_mkdir, (long)p_vend, 0755);
    r = sc5(SYS_mount, (long)p_vmtd, (long)p_vend, (long)p_jf, 0, (long)"rw");
    r2 = 0;
    if (r < 0)
        r2 = sc5(SYS_mount, (long)p_vmtd, (long)p_vend, (long)p_jf, 32 /* MS_REMOUNT */, (long)"rw");
    /* The remount's return used to be thrown away here, and the tag reported the
     * FIRST mount's errno even when the remount succeeded. Record 1 carries the
     * verdict that actually decides the mount. */
    wmark(1, r < 0 ? r2 : r);
    tg |= (((unsigned long)(-(r < 0 ? (r2 < 0 ? r2 : 0) : 0))) & 0xfu) << 4;
    tag();
    if (r == 0 || r2 == 0) {
        sc2(SYS_mkdir, (long)p_vetc, 0755);
        fd = sc3(SYS_open, (long)p_vrc, 0x241 /* WRONLY|CREAT|TRUNC */, 0644);
        if (fd >= 0) {
            sc3(SYS_write, fd, (long)marker, sizeof(marker) - 1);
            sc2(SYS_close, fd, 0);
            tg |= 1ul << 8;
        } else {
            tg |= 2ul << 8;
        }
        tag();
    }

    /*
     * Breadcrumb shadows of four vendor boot scripts: each logs a line to
     * /boot.log (in the overlay upper, so it survives) and then execs the real
     * script. The last line after a run names the last script the vendor's
     * procd reached on our kernel.
     */
    sc2(SYS_mkdir, (long)p_vrd, 0755);
    sc2(SYS_mkdir, (long)p_vid, 0755);
    write_test_masks();
    wfile("/vendor/upper/etc/rc.d/S10boot", sh_boot, 0755);
    wfile("/vendor/upper/etc/init.d/luofu", sh_luofu, 0755);
    wfile("/vendor/upper/etc/rc.d/luofu", sh_luofu, 0755);
    wfile("/vendor/upper/etc/rc.d/S18hyfibrd", sh_hyfi, 0755);
    wfile("/vendor/upper/etc/rc.d/S20network", sh_net, 0755);
    wfile("/vendor/upper/etc/rc.d/S95done", sh_done, 0755);

    /*
     * Is there a pstore backend at all? Mounting the pstore filesystem succeeds
     * only when one registered, and that answer decides whether a panic capture
     * on this kernel can ever store anything. It goes into the vendor upper so
     * the vendor's next boot can read it.
     */
    sc2(SYS_mkdir, (long)p_pst, 0755);
    r = sc5(SYS_mount, (long)"pstore", (long)p_pst, (long)"pstore", 0, 0);
    tg |= (r == 0 ? 1ul : 2ul) << 21;
    tag();
    wfile("/vendor/upper/pstore-check.txt", r == 0 ? ps_ok : ps_no, 0644);

    /*
     * Release the device properly (not MNT_DETACH): the vendor's mount_root
     * mounts this same partition a second later, and a lazily detached
     * superblock still holding it is a conflict. The jffs2 write path works
     * since the DTS gave rootfs_data its real size, so the sync completes.
     */
    load_vendor_modules();

    sc2(SYS_umount2, (long)p_vend, 0);

    /* devtmpfs rides into the new root so the vendor's preinit can see /dev. */
    sc2(SYS_mkdir, (long)p_ndev, 0755);
    r = sc5(SYS_mount, (long)p_sdev, (long)p_ndev, 0, MS_MOVE, 0);
    tg |= (((unsigned long)(-r)) & 0xfu) << 12;
    tag();

    r = sc1(SYS_chdir, (long)p_low);
    tg |= (((unsigned long)(-r)) & 0xfu) << 16;
    tag();
    if (r != 0)
        fail(2);

    r = sc2(SYS_pivot, (long)p_dot, (long)p_dot);
    tg |= (((unsigned long)(-r)) & 0xfu) << 20;
    tag();
    if (r != 0) {
        /* pivot_root refused: chroot gives the vendor init the same root. */
        r = sc1(SYS_chroot, (long)p_dot);
        tg |= (((unsigned long)(-r)) & 0xfu) << 24;
        tag();
        if (r != 0)
            fail(3);
    } else {
        sc2(SYS_umount2, (long)p_dot, 2 /* MNT_DETACH */);
    }

    if (sc1(SYS_chdir, (long)p_root) != 0)
        fail(4);

    tg |= 1ul << 28;
    tag();

    sc3(SYS_execve, (long)p_init, (long)argv, (long)envp);
    sc3(SYS_execve, (long)p_pre, (long)argv_sh, (long)envp);

    fail(5);
}