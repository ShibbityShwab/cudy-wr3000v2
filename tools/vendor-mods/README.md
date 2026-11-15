# Vendor module fixtures

These two modules (`hi_kmdio.ko`, `hi_swa.ko`) are vendor binaries kept only as lab
fixtures for the `.plt` load recipe. They are not our work and are not part of the
clean-room drivers. Do not redistribute them.

The recipe that makes them load on our kernel is
`opensource/docs/VENDOR-STACK-ON-MAINLINE.md`: add zero-size `.plt` and `.init.plt`
sections with `objcopy`, and keep `module_alloc` in the near region so a PLT entry is
never needed.
