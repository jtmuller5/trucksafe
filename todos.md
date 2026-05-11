# Manual setup for sample-batch-01 transfer

## Authorize the MacBook's SSH key on the GPU rig (one-time)

The MacBook's existing key at `~/.ssh/personal/id_ed25519` is not in the rig's
`authorized_keys`, and password auth requires an interactive prompt the agent
can't fulfill. Pick one:

### Option A — `ssh-copy-id` (simplest, prompts for the rig password once)
```bash
ssh-copy-id -i ~/.ssh/personal/id_ed25519.pub joemuller@100.77.220.87
```

### Option B — paste the pubkey into the rig's authorized_keys yourself
Pubkey to add (one line):
```
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPMyKonqY/7Icj+WtnqhIn3Qdnb66Oj8rJL4g/EACyd7 jtmuller5@gmail.com
```
Append it to `~/.ssh/authorized_keys` on the rig (`mkdir -p ~/.ssh && chmod 700 ~/.ssh`,
then `chmod 600 ~/.ssh/authorized_keys`).

### Option C — load a different key into ssh-agent
If you've got a different key that's already on the rig, run:
```bash
ssh-add ~/.ssh/your-rig-key
```
and tell me which key so I can update the rsync command.

## Verify auth works
After whichever option, run:
```bash
ssh joemuller@100.77.220.87 'echo rig_ok && hostname'
```
Should print `rig_ok` and the rig's hostname without a password prompt.

## Then say "continue" and I will:
1. Pre-create `~/projects/trucksafe/training/data/images/sample-batch-01/` on the rig
2. Rsync the 2.9 GB batch over Tailscale (estimated minutes, not hours)
3. Verify per-category counts match and md5-spot-check 15 random files
4. Write `training/data/MANIFEST_sample-batch-01.md` and commit it (no push)
