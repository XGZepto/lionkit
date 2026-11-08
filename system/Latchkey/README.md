# Latchkey

A menu bar app that keeps a Lion Mac on Wi-Fi networks that offer WPA2 and WPA3 together
("transition" networks). Lion mistakes them for WPA2 Enterprise and won't join them. Latchkey
rewrites the network's scan record so it offers only WPA2-PSK and then joins. When the Mac drops off
Wi-Fi and Lion doesn't get it back, Latchkey rejoins a remembered network. It leaves the Mac alone
while Wi-Fi is off or the Mac is on another network.

You choose a network in the menu and type its password once. Latchkey keeps the password in the
login keychain (service "Latchkey", account = network name). It must run in the GUI session,
so it opens as a login item, not as a LaunchAgent started over SSH.

| File | What it holds |
|---|---|
| `main.py` | The status item, the menu, the join dialog, and the rejoin logic (poll every 5 s, give Lion 8 s first, back off 30 s → 5 min after failures) |
| `wifi.py` | CoreWLAN: status, scan, network classification, and the join trick |
| `art.py` | The menu bar key, lock, signal fan and status lights |
| `icon.py` | The app icon: a brass key whose bow is the Wi-Fi fan |

```bash
tools/deploy.sh system/Latchkey
tools/launch.sh relaunch "Latchkey"
```

## Demo mode for screenshots

Demo mode uses made-up networks. It never joins anything and never touches the keychain or the
login items. Turn it off again with `defaults delete page.zepto.latchkey`.

```bash
ssh lionmac defaults write page.zepto.latchkey Demo -bool YES
ssh lionmac defaults write page.zepto.latchkey DemoState failed   # connected, joining, failed, off, away, fresh
ssh lionmac defaults write page.zepto.latchkey DebugOpen preview  # or join, error, save, other, joining
```

`DebugOpen preview` opens a window with the menu's custom rows, because an open menu can't be
captured over SSH. `DemoJoinSeconds` sets how long a fake join takes.
