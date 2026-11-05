# cmdb-nginx-agent

Agent de discovery Nginx pour la CMDB : lit la configuration effective de Nginx (`nginx -T`) sur le reverse-proxy, et pousse dans NetBox, via Diode, un service par `server_name` (ports `listen`, cible amont `proxy_pass` résolue à travers les blocs `upstream`). Aucun SSH : l'agent tourne sur le reverse-proxy et pousse vers la CMDB.

*Nginx discovery agent: reads `nginx -T` on the reverse proxy and pushes one NetBox service per `server_name` (listen ports, `proxy_pass` upstream) through Diode. No SSH: the agent runs on the proxy and pushes.*

Ce qui est envoyé, pour chaque vhost : un `ipam.Service` nommé comme le hostname, parent = la VM du reverse-proxy (telle qu'importée par Proxmox), `port_mappings`, tag `nginx-agent`, custom field `upstream_target`. Le plugin Cloudflare s'en sert ensuite pour suivre `cloudflared → Nginx → service final`.

## Installation sur revers-proxy (Debian/Ubuntu)

```bash
sudo apt install -y python3-venv git
sudo python3 -m venv /opt/cmdb-nginx-agent
sudo /opt/cmdb-nginx-agent/bin/pip install "git+https://github.com/joblinours/NetBox-plugin.git@main#subdirectory=agents/nginx-agent"
```

Configuration (`/etc/cmdb-nginx-agent.env`, mode 600, valeurs issues des variables de la stack rangées dans Vaultwarden) :

```bash
sudo install -m 600 /dev/null /etc/cmdb-nginx-agent.env
sudoedit /etc/cmdb-nginx-agent.env   # modèle : cmdb-nginx-agent.env.example
```

| Variable | Valeur |
| --- | --- |
| `DIODE_TARGET` | `grpc://192.168.1.13:10001/diode` |
| `DIODE_CLIENT_ID` / `DIODE_CLIENT_SECRET` | `nginx-agent` / `DIODE_CLIENT_SECRET_NGINX_AGENT` |
| `NGINX_AGENT_HOST_NAME` | nom de la VM dans NetBox (ex. `revers-proxy`) |
| `NGINX_AGENT_CLUSTER` | nom du cluster Proxmox dans NetBox (évite de créer une VM en double) |
| `NGINX_AGENT_HOST_TYPE` | `vm` (défaut) ou `device` |
| `NETBOX_URL` / `NETBOX_TOKEN` | `http://192.168.1.13:10000` / `CMDB_TOKEN_NGINX_AGENT` (statut pour Zabbix) |

Test à blanc, puis activation du timer quotidien :

```bash
sudo /opt/cmdb-nginx-agent/bin/cmdb-nginx-agent --env-file /etc/cmdb-nginx-agent.env --dry-run
sudo cp systemd/cmdb-nginx-agent.service systemd/cmdb-nginx-agent.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now cmdb-nginx-agent.timer
sudo systemctl start cmdb-nginx-agent.service && journalctl -u cmdb-nginx-agent -n 20
```

Les fichiers systemd sont dans `agents/nginx-agent/systemd/` du dépôt. Le timer tourne 5 min après le démarrage puis chaque jour à 04:00 ; chaque exécution (succès ou échec) est remontée à NetBox (source `nginx`), donc à Zabbix.

Mise à jour : relancer la commande `pip install` avec `--upgrade`.

## Tests

```bash
pip install -e '.[test]' && pytest tests
```

## Licence

MIT
