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
#define SYS_write    4
#define SYS_open     5
#define SYS_close    6
#define SYS_chdir    12
#define SYS_mount    21
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
static const char sh_boot[] =
    "#!/bin/sh\n"
    "echo \"S10boot $(date +%s) $(uname -v)\" >> /boot.log\n"
    "exec /etc/init.d/boot \"$@\"\n";
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
     * DUMP BEFORE THE VENDOR'S done RUNS (2026-11-13).
     *
     * The vendor's done writes 384 KiB of /dev/random to /etc/mount_protect
     * before it ever reaches rc.local, and every reset in this session lands
     * inside that window - which is why no marker ever wrote. The net dump and
     * the kernel-ran line therefore go first, straight into the overlay upper,
     * so the measurement survives even if the dd takes the box down.
     */
    "OUT=/overlay/upper/net-dump-final.txt\n"
    "{\n"
    "  echo \"=== kernel ===\"; cat /proc/version; uname -v\n"
    "  echo \"=== uptime ===\"; cat /proc/uptime\n"
    "  echo \"=== ip link ===\"; ip link 2>&1\n"
    "  echo \"=== ip addr ===\"; ip addr 2>&1\n"
    "  echo \"=== bridge ===\"; brctl show 2>&1\n"
    "  echo \"=== iw dev ===\"; iw dev 2>&1\n"
    "  echo \"=== dmesg net ===\"; dmesg | grep -iE 'gmac|luofu|mdio|phy|eth[0-9]|netdev' | tail -40 2>&1\n"
    "  echo \"=== clocks ===\"; ls /sys/kernel/debug/clk 2>&1 | head -20\n"
    "  echo \"=== modules ===\"; lsmod 2>&1 | head -25\n"
    "  echo \"=== cells ===\"; /sbin/devmem 0x10100C94 32 2>&1; /sbin/devmem 0x10100C80 32 2>&1; /sbin/devmem 0x10100C88 32 2>&1; /sbin/devmem 0x10100C18 32 2>&1\n"
    "  echo \"=== gmac ===\"; dmesg | grep -iE 'luofu-gmac|luofu_gmac|Hi-GEMAC|gemac' | tail -30 2>&1\n"
    "} >> $OUT 2>&1\n"
    "echo \"$(date +%s) $(uname -v) shadow\" >> /overlay/upper/kernel-ran-final.log\n"
    "sync\n"
    "exec /etc/init.d/done \"$@\"\n"
    ;
static const char p_jf[]    = "jffs2";
static const char p_mem[]   = "/dev/mem";
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

static void wfile(const char *path, const char *s, long mode)
{
    long fd = sc3(SYS_open, (long)path, 0x241 /* WRONLY|CREAT|TRUNC */, mode);
    long n = 0;

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
    long r;
    long fd;

    tg = 1;
    tag();

    sc2(SYS_mkdir, (long)p_vend, 0755);
    r = sc5(SYS_mount, (long)p_vmtd, (long)p_vend, (long)p_jf, 0, 0);
    tg |= (((unsigned long)(-r)) & 0xfu) << 4;
    tag();
    if (r == 0) {
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
    wfile("/vendor/upper/etc/rc.d/S10boot", sh_boot, 0755);
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

    start_petter();

    tg |= 1ul << 28;
    tag();

    sc3(SYS_execve, (long)p_init, (long)argv, (long)envp);
    sc3(SYS_execve, (long)p_pre, (long)argv_sh, (long)envp);

    fail(5);
}
