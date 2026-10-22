# Public ArchRivet MCP with the fine-tuned Laya model

The public URL uses two free services: a Cloudflare Worker forwards MCP over HTTPS; an Oracle Always Free Ampere A1 VM runs ArchRivet and the 322M-parameter merged Laya checkpoint on CPU. The Worker never substitutes deterministic-only reviews. This is a small experimental beta, not guaranteed permanent uptime or production accuracy.

Create an Oracle Cloud Always Free account and a **VM.Standard.A1.Flex** Ubuntu 24.04 instance with **2 OCPUs and 12 GB RAM** in the home region. Allocate a boot volume within the free block-volume allowance and assign a public IPv4 address. In the Oracle virtual network, allow inbound TCP 22 for your SSH access and 80/443 for Caddy. Keep ports 8765 and 8789 closed to the internet. Oracle may have no A1 capacity in a region, and can reclaim idle free instances.

After SSH login, clone the ArchRivet repository and run the bootstrap from that checkout:

```bash
git clone --branch feature/laya-public-mcp --single-branch https://github.com/Ujjansh05/archrivet.git
cd archrivet
sudo bash scripts/oracle_laya_bootstrap.sh <YOUR_PUBLIC_IP>.sslip.io
```

The bootstrap installs the project, the pinned CPU PyTorch build, downloads and verifies the released merged checkpoint, configures only the Laya backend, and starts two systemd services. It also configures Caddy for HTTPS. `sslip.io` supplies a free DNS name from the public IP; if the IP changes, update the hostname and Cloudflare origin secret. Using a domain you own is more reliable. On first start, model checksum verification and warmup can take several minutes. The MCP port opens only after a real Laya decision succeeds.

Check on the VM:

```bash
sudo systemctl status archrivet-api archrivet-mcp caddy
sudo journalctl -u archrivet-mcp -n 50 --no-pager
curl -i https://<YOUR_PUBLIC_IP>.sslip.io/mcp
```

The unauthenticated `curl` must return **401**, which shows the private model host is not open to direct callers. The gateway adds the private bearer token when it forwards public MCP calls. See [gateway setup](../cloudflare/README.md) for deployment and end-to-end checks.

OpenAI's public directory requires a stable HTTPS Streamable HTTP endpoint, domain verification, working tool tests and review materials. Direct custom MCP connections in ChatGPT are limited by account or workspace plan; directory approval is a separate process. Keep model limitations visible: its calibration is unvalidated and it has failed separate regression checks. A successful MCP handshake does not establish review accuracy.
