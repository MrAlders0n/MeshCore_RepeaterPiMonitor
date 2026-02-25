# RepeaterWatch

## Sudoers Configuration

The firmware flash feature requires the `meshcoremon` service user to stop and start `SerialMux` and `mctomqtt` via `systemctl`. Add a sudoers drop-in file so these specific commands run without a password prompt:

```bash
sudo visudo -f /etc/sudoers.d/meshcoremon
```

Contents:

```
meshcoremon ALL=(ALL) NOPASSWD: /usr/bin/systemctl stop SerialMux, /usr/bin/systemctl stop mctomqtt, /usr/bin/systemctl start SerialMux, /usr/bin/systemctl start mctomqtt
```