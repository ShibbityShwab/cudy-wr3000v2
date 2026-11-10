# Cudy WR3000 v2.0: anyone holding the fleet bdinfo secret can log into the MQTT broker and run commands as root

Found and confirmed on my own device during personal firmware research, 2026-11-08.

This covers two linked issues:

- CVE-2026-71960: the Mosquitto JWT plugin accepts a forged token signed with the fleet-wide bdinfo `secret`.
- CVE-2026-71961: a forged satellite credential can publish a command that the admin cmagent executes as root. No second physical node is required.

## Target

- Cudy WR3000 v2.0 (HiSilicon "luofu" platform, OpenWrt 22.03.6 based firmware, target `hisilicon/luofu`, kernel 5.10.201).
- Verified against firmware 2.4.15-20251030-114751 (R116).
- I have no evidence of a fixed release for either issue. The repo's 2.5.24 fix belongs to the system time command injection, a separate bug in a different file. Treat the Mosquitto authentication and command-trust problems as unpatched until the vendor says otherwise.

## The broker

The router runs Mosquitto on two ports. Port 1883 takes plain MQTT with JWT authentication, and 8883 takes TLS with client certificates. The effective configuration on the tested build is:

    allow_anonymous false
    auth_plugin /usr/lib/auth_plugin_jwt.so

Two settings decide who gets in. Anonymous clients are refused outright. Every other client has to pass the authentication plugin. The plugin does not grant every topic: its `acl_check` returns `MOSQ_ERR_PLUGIN_DEFER`, so the broker's `/etc/mosquitto/aclfile.conf` is enforced.

The ACL has two users and a fixed role/topic matrix:

    user cudydevice
    topic read  router/+/000000000000/+/+/+
    topic write router/000000000000/+/+/+/+

    user admincudydevice
    topic read  router/000000000000/+/+/+/+
    topic write router/+/000000000000/+/+/+
    topic read  $SYS/#

The factory bdinfo on this unit carries the string `cudydevice` as its `deviceid`. The 12-digit `000000000000` is the controller sentinel used in the topic tree, not a per-unit random ID and not the bdinfo deviceid. That distinction matters: the plugin performs substring checks, but the ACL `user` entries are exact, so the working satellite username is `cudydevice`, not `admincudydevice-000000000000`.

The plugin itself is `/usr/lib/auth_plugin_jwt.so`. On this unit its sha256 is `4b5018a5d6ffdbb3faa46c377ff87445279e508ee44d1677d6d2909b15ff8355`, identical to the copy recovered from the official 2.4.15 rootfs dump.

## What the plugin checks

`mosquitto_auth_unpwd_check` sits at offset `0x3318` in the 2.4.15 build. It runs four checks, in order:

1. The MQTT username contains the bdinfo `deviceid` (`cudydevice`). This is a plain `strstr`.
2. The supplied password parses as a JWT using HS256, HS384 or HS512, and the signature verifies against the HMAC key stored as `secret` in the bdinfo partition.
3. The token's `exp` grant is at least `1577826000`, which is 2019-12-31T21:00:00Z. The plugin never compares `exp` to the current clock. It checks the floor and nothing else.
4. The `username` grant inside the token contains the bdinfo `deviceid`, again by `strstr`.

If all four pass, the function returns SUCCESS. `acl_check` at `0x3310` then returns `MOSQ_ERR_PLUGIN_DEFER` (17), which hands topic authorization to the ACL file above. The plugin is not an allow-all ACL.

Two consequences fall out of the authentication code. Any expiry value at or above the floor is accepted forever, so a token minted with `exp` set to 2033 works in 2033. And because the checks are substring tests, a longer username such as `admincudydevice-000000000000` can authenticate. It cannot use topics, however, because the ACL `user` directive requires the exact `cudydevice` or `admincudydevice` string. An earlier test that stopped at CONNACK rc=0 and printed "subscribed" was reading a broker success for authentication, not a granted subscription.

## Where the signing key comes from

The HMAC key is the `secret` value in the bdinfo MTD partition. That partition is not random per unit. `libbdinfo.so` ships the literal `88T3j05dtFu8=`, uses it as a DES key through the OpenSSL `DES_string_to_key` variant, and decrypts the partition with a zero IV after a 4-byte container header.

So anyone who can read bdinfo off one device and run the same decryption recovers two things: that device's `secret` and its `deviceid`. Both are fleet values, not unit values, which is the root of the problem below.

## Topic and command contract

The mesh topic is:

    <prefix>/<dst_did>/<src_did>/<seq>/<app>/<event>

with `prefix = router`. The handler path is:

    /usr/lib/lua/cmagent/<app>/<event>.lua

For `router/command`, `command.lua` decodes the JSON payload, checks that `src_did` equals the controller sentinel `000000000000`, and passes the JSON `cmd` field verbatim to `io.popen`. It does not check `dst_did`, does not authenticate the payload, and does not quote the command. The only gate is the `src_did` equality check. The `reply` field is optional and only controls whether the encoded result is returned to the caller.

The admin (`-a`) has device id `000000000000` and subscribes to `router/000000000000/+/+/+/+`. A satellite subscribes to `router/<own_did>/000000000000/+/+/+/+`. Both subscriptions happen immediately in the CONNACK callback; there are exactly two `mosquitto_subscribe` call sites in the binary, and no announcement or role-negotiation path. The controller identity is a string convention in the topic, not an authenticated identity.

## Proof of concept

The token shape is ordinary:

    header  : {"alg": "HS256", "typ": "JWT"}
    payload : {"exp": 1999999999, "username": "cudydevice"}

The steps look like this:

1. Dump the bdinfo partition from a device you own and decrypt it with `tools/decrypt_bdinfo.py`. You get `secret = <BDINFO-SECRET>` and `deviceid = cudydevice`.
2. Forge a satellite token with `tools/forge_jwt.py --deviceid cudydevice --role satellite --secret '<BDINFO-SECRET>'`.
3. Connect to port 1883 with username `cudydevice` and the token as the password. CONNACK is rc=0.
4. Subscribe to the satellite read pattern `router/+/000000000000/+/+/+`, or simply to the reply pattern for the command you are about to send. `router/#` is not in the ACL and will not be granted.
5. Publish to `router/000000000000/000000000000/7/router/command` with the JSON payload below plus a trailing NUL byte.
6. The admin's `router/000000000000/+/+/+/+` subscription receives it, `command.lua` trusts `src_did=000000000000`, and `io.popen` runs the command as root.

The payload that was verified:

    {"cmd":"id > /tmp/omo-71961-verify.txt","reply":1}\x00

The trailing NUL is required by the C-side JSON sniff. The receive path tests `payload[payloadlen-2] == '}'` because the stock publisher includes the NUL in `payloadlen`. A bare JSON publish has `payloadlen = strlen(JSON)`, so the test sees the character before `}` and fails. The non-JSON path then treats `src_did=000000000000` as a crypt-list peer, AES-CBC decrypts the plaintext, and Lua fails with `Expected value but found invalid token at character 1`. No command runs in that path.

Observed on the device:

    $ cat /tmp/omo-71961-verify.txt
    uid=0(root) gid=0(root)

    daemon.info cmagent[24863]: shell cmd id > /tmp/omo-71961-verify.txt

The reply arrives on the wire:

    topic:   router/000000000000/000000000000/1794161977/router/reply
    payload: {"message":"success","data":"","code":0}\x00

The command ran as root (`uid=0`), not as an unprivileged cmagent user. The handler's `io.popen` is the execution primitive; the topic field is the only authorization decision.

## No second node is required

This unit has no satellite. `/var/run/cmagent` contains only `000000000000`, and cmagent runs with `-a`. The exploit does not need a satellite because the admin's own wildcard subscription receives the message, and the satellite role's ACL write pattern allows setting `dst_did=000000000000` with an arbitrary `src_did`.

The legitimate `sync_command` path is the same trust decision in the other direction. `sync_command` loops over `/var/run/cmagent` and skips `000000000000`, so on a standalone admin it sends nothing. The exploit goes around that loop through the broker and uses the satellite role's write permission.

The fix boundary is the topic trust: a command is treated as controller-originated because the third topic field says `000000000000`, with no cryptographic binding to the publisher. The ACL's role split is real, but the two role patterns compose into the exploit: the satellite can write the controller-addressed command topic, and the admin reads it.

## Why the key matters beyond one router

The bdinfo `secret` is a fleet key. Every unit shipped from the same firmware line decrypts and signs with it. A single leaked or extracted value authenticates against every unit that trusts it, and the topic identities (`dst_did`/`src_did`) are attacker-chosen within the ACL patterns, not secrets.

That leaves the threat model with one real fence, and it is a good fence: port 1883 has to be reachable. On this unit the listener binds `0.0.0.0:1883`, but the WAN firewall zone has `input='REJECT'`, so the tested access was LAN-only. Any arrangement that exposes 1883 more widely, a misconfigured firewall, a bridged guest network, or a mesh deployment that carries the broker across links, turns a fleet secret into fleet-wide broker access and root command execution.

## Impact

- Anyone with the bdinfo `secret` and network reachability to port 1883 can authenticate as the `cudydevice` satellite role, publish a controller-addressed command, and get root command execution on the admin. No second node is needed.
- The same key can authenticate as the `admincudydevice` role, which can read the admin command feed and `$SYS/#`, and write to a satellite's command topic. The ACL limits the topics but does not require a per-unit secret.
- The token expiry floor is fixed, so forged tokens do not decay. Recovery means rotating the bdinfo `secret`, which is a firmware-level change, not a configuration change on one box.
- The broker's 1883 listener is plaintext. The WAN firewall is the only network fence on the tested unit; an exposed broker is directly exploitable.

## Notes

- Live checks came over direct SSH after the restored network root. The plugin analysis used the offline rootfs dump, and the broker config was read on the device.
- Integrity check: the live `/usr/sbin/cmagent`, `/usr/lib/lua/cmagent/router/command.lua`, `/usr/sbin/sync_command`, and `/usr/lib/auth_plugin_jwt.so` match the 2.4.15 rootfs copies.
- The bdinfo decryption constants come from `libbdinfo.so` 2.4.15. If a later build changes the literal, the step from a device dump to the key changes, but the plugin checks and the fleet key model stay where they are unless the vendor rotates the `secret`.
- The command in the live test was a benign `id` redirect. The router was not rebooted, Wi-Fi was not touched, `cmagent.mqtt.admin` was not changed, and cmagent was not restarted. Final state: 2 wiphys, 6 Wi-Fi interfaces, `admin=1`, cmagent running with `-a`, no `.omo-off` leftovers.
- Evidence: `dumps/router-20261108/mqtt-command-chain-report.md` and `dumps/router-20261108/evidence/` (transcript, plugin integrity, ACL, final health).

## Disclosure

Documented here for reference. The vendor has not been contacted about this finding. The bdinfo secret, forged tokens and passwords are deliberately omitted; the placeholders above are not runnable.
