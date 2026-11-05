# NetBox-plugin — CMDB homelab (NetBox + Diode)

🇬🇧 [English version](README.en.md)

Ce dépôt contient tout ce qu'il faut pour faire tourner la CMDB du homelab : NetBox comme source de vérité, alimentée automatiquement par Diode et par des plugins. Une seule stack Portainer, sans aucun fichier à déposer sur l'hôte.

| Dossier | Contenu |
| --- | --- |
| `plugins/netbox-cloudflare-tunnel/` | Plugin maison : synchronise les hostnames publics des tunnels Cloudflare et indique pour chacun le chemin d'exposition (cloudflared direct ou via Nginx) et le service cible |
| `plugins/netbox-cmdb/` | Plugin maison : modèle de données de base (custom fields), comptes de service et tokens, sync Proxmox planifiée, santé des sources pour Zabbix |
| `plugins/netbox-cmdb-mcp/` | Plugin maison : serveur MCP en lecture seule pour Claude Code (hôtes, IPs et ports pris/libres, URLs, DNS, conteneurs) |
| `plugins/netbox-cmdb-export/` | Plugin maison : export de la CMDB en Markdown, PDF, JSON, et graphe topologique Mermaid / PNG / SVG |
| `plugins/netbox-adguard/` | Plugin maison : réécritures DNS d'AdGuard Home → noms locaux dans NetBox et dans netbox-plugin-dns |
| `plugins/netbox-docker-inventory/` | Plugin maison : hôtes Docker, stacks, conteneurs (même silencieux), réseaux internes, ports, volumes |
| `agents/nginx-agent/` | Agent de discovery installé sur `revers-proxy` : lit `nginx -T` et pousse les vhosts dans NetBox via Diode |
| `agents/docker-agent/` | Agent Docker (dans la stack pour le LXC, et `deploy/docker-agent.compose.yml` pour chaque autre hôte Docker) |
| `image/netbox/` | Recette de l'image NetBox (image officielle + plugins tiers + plugins maison) |
| `image/diode-gateway/`, `image/diode-bootstrap/`, `image/orb-agent/`, `image/docker-agent/` | Petites images qui embarquent la configuration de Diode et d'orb-agent (pour ne rien déposer sur l'hôte) |
| `deploy/` | Fichier de stack (`docker-compose.yml`) et exemple de variables (`stack.env.example`) |
| `tools/generate-env.py` | Génère toutes les variables de la stack avec des secrets aléatoires |
| `monitoring/zabbix/` | Template Zabbix 7.0 (disponibilité NetBox/API/Diode et échec de chaque source) |
| `.github/workflows/build.yml` | Lint, tests sur une instance NetBox 4.7, recherche de secrets, build et push GHCR |

## Architecture

```
                         ┌──────────────────────── stack Portainer « cmdb » (LXC 192.168.1.13) ─────────────────────────┐
 navigateur ── :10000 ─▶ │ netbox ── netbox-worker (jobs planifiés : Proxmox, Cloudflare)    postgres  valkey           │
                         │   ▲  └── API Proxmox (proxmox2netbox)  └── API Cloudflare (plugin maison)                     │
                         │   │ API plugin Diode                                                                           │
                         │ diode-reconciler ◀── diode-ingester ◀── diode-gateway (nginx, gRPC + OAuth2) ◀── :10001 ─────┼── nginx-agent (revers-proxy)
                         │                         diode-auth ── hydra ── diode-postgres, diode-redis   ▲                │
                         │ orb-agent (réseau hôte, nmap 192.168.1.0/24) ─────────────────────────────────┘                │
                         └────────────────────────────────────────────────────────────────────────────────────────────────┘
 Zabbix ── :10000/api/plugins/cmdb/health/ et :10001
```

Seuls deux ports sont publiés : l'interface NetBox (`NETBOX_PORT`, 10000) et l'entrée gRPC de Diode (`DIODE_GRPC_PORT`, 10001). Tout le reste reste sur le réseau interne de la stack. orb-agent tourne en réseau hôte pour voir le LAN et joint Diode et NetBox par leurs ports publiés.

### Sources automatiques

| Source | Comment | Fréquence | Statut remonté (Zabbix) |
| --- | --- | --- | --- |
| Proxmox | Plugin `proxmox2netbox`, endpoint créé au démarrage depuis les variables ; job système `CMDB - Proxmox sync` dans le worker. Tous les nœuds du cluster sont lus via l'API : un 5ᵉ nœud apparaît sans rien changer | `PROXMOX_SYNC_INTERVAL` (1440 min) | source `proxmox` |
| Scan réseau | orb-agent (nmap) → Diode. Un scan au démarrage, puis chaque nuit (`SCAN_SCHEDULE`). IPs vivantes + ports ouverts (dans les commentaires de l'IP) | quotidienne | source `network-scan` |
| Cloudflare | Plugin `netbox-cloudflare-tunnel` : lit l'ingress des tunnels gérés dans le dashboard (token lecture seule), crée ou retrouve le service cible et renseigne `URL publique` et `Chemin d'exposition` | `CLOUDFLARE_SYNC_INTERVAL` (1440 min) | source `cloudflare` |
| Nginx | `cmdb-nginx-agent` sur revers-proxy (timer systemd) → Diode. Un service par `server_name`, avec ports et cible amont (`proxy_pass`) | quotidienne | source `nginx` |

| AdGuard Home | Plugin `netbox-adguard` : réécritures DNS → IP/hôte (custom field « Domaines locaux ») et enregistrements A/CNAME dans netbox-plugin-dns | `ADGUARD_SYNC_INTERVAL` (1440 min) | source `adguard` |
| Docker | `cmdb-docker-agent` sur chaque hôte Docker → plugin `netbox-docker-inventory` (conteneurs, stacks, réseaux internes, ports publiés → services NetBox avec « Stack Portainer ») | toutes les heures | source `docker-<hôte>` |

Comment le chemin d'exposition est déterminé : si l'origine d'un hostname Cloudflare est l'IP de revers-proxy (`NGINX_PROXY_HOSTS`), le hostname est « via Nginx » ; le plugin retrouve le vhost poussé par l'agent Nginx, lit sa cible amont et rattache l'URL publique au service final (par exemple `cloud.example.com` → revers-proxy:443 → nextcloud:11000). Sinon il est « cloudflared direct » et rattaché au service de la VM d'origine. Le plugin crée le service s'il n'existe pas sur le port d'origine.

Toutes les sources sont idempotentes : une deuxième exécution ne crée aucun doublon (vérifié par les tests et sur une stack réelle).

## Utiliser la CMDB

- **Claude Code (MCP)** : `claude mcp add --transport http --scope user cmdb http://192.168.1.13:10000/api/plugins/mcp/ --header "Authorization: Bearer <CMDB_TOKEN_MCP>"`. Claude peut alors vérifier un port ou une IP, proposer des ports/IPs libres, lire la fiche d'un hôte, lister les URLs, noms DNS et conteneurs. Détails : [plugins/netbox-cmdb-mcp/README.md](plugins/netbox-cmdb-mcp/README.md).
- **Export** : menu *Plugins > Export CMDB* (Markdown, PDF, JSON, graphe Mermaid / PNG / SVG), ou `GET /api/plugins/export/<format>/` avec un token. Détails : [plugins/netbox-cmdb-export/README.md](plugins/netbox-cmdb-export/README.md).

## Déploiement (première fois)

1. **Créer les accès en lecture seule** :
   - Proxmox : `Datacenter > Permissions > Users` : créer `netbox@pve`, puis `API Tokens` : token `cmdb` *sans* « Privilege Separation », et donner le rôle `PVEAuditor` sur `/` à l'utilisateur. Noter le secret.
   - Cloudflare : `My Profile > API Tokens > Create Token` avec la permission `Account > Cloudflare Tunnel > Read` sur le compte. Noter aussi l'Account ID.
2. **Générer les variables** (sur n'importe quel poste avec Python 3) :
   ```bash
   python3 tools/generate-env.py > cmdb.env
   ```
   Compléter `PROXMOX_*`, `CLOUDFLARE_*`, `NGINX_PROXY_HOSTS` (IP de revers-proxy) et `NETBOX_ADMIN_USER`. Ranger le fichier complet dans Vaultwarden, ne jamais le committer.
3. **Créer la stack dans Portainer** : `Stacks > Add stack > Repository`
   - Repository URL : `https://github.com/joblinours/NetBox-plugin`, référence `refs/heads/main`
   - Compose path : `deploy/docker-compose.yml`
   - Environment variables > *Advanced mode* : coller le contenu de `cmdb.env`
   - Deploy. Les images sont publiques sur GHCR : aucun identifiant de registre.
4. **Premier démarrage** (quelques minutes, migrations comprises) : NetBox applique les migrations, crée le compte admin, puis `cmdb_bootstrap` crée les custom fields, les comptes de service `svc-*` avec leurs tokens et l'endpoint Proxmox. Les clients OAuth2 de Diode sont créés par `diode-bootstrap`.
5. **Vérifier** : se connecter sur `http://192.168.1.13:10000` ; `Diode > Settings` affiche la cible Diode et `Diode > Client Credentials` s'ouvre sans erreur (preuve que NetBox s'authentifie auprès de Diode) ; `CMDB > Source health` liste l'état de chaque source. Les clients OAuth2 créés par la stack (`orb-agent`, `nginx-agent`) sont gérés par les variables et n'apparaissent pas dans cette liste, qui ne montre que les clients créés depuis l'interface.
6. **Installer l'agent Nginx** sur revers-proxy : voir [agents/nginx-agent/README.md](agents/nginx-agent/README.md).
7. **Agents Docker** sur les autres hôtes Docker : voir [agents/docker-agent/README.md](agents/docker-agent/README.md) (celui du LXC tourne déjà dans la stack).
8. **Zabbix** : importer `monitoring/zabbix/cmdb_netbox_template.yaml`, l'associer à l'hôte de la CMDB et renseigner la macro `{$CMDB.TOKEN}` avec `CMDB_TOKEN_ZABBIX`.

> Le compte admin n'est créé qu'au premier démarrage : s'il existe déjà, il n'est plus touché (changer son mot de passe dans NetBox, pas dans la variable).

## Variables principales

Toutes les variables sont listées et commentées dans [deploy/stack.env.example](deploy/stack.env.example). Les secrets n'utilisent que `[A-Za-z0-9]`, donc rien ne casse une chaîne de connexion.

| Variable | Rôle |
| --- | --- |
| `CMDB_IMAGE_TAG` | `latest` (main), `dev`, une version `1.2.3`, ou `sha-<commit>` |
| `DOCKER_HOST_IP`, `BIND_ADDRESS` | IP de l'hôte Docker ; `BIND_ADDRESS` permet de n'écouter que sur l'interface LAN |
| `NETBOX_PORT`, `DIODE_GRPC_PORT` | Ports publiés (10000 et 10001 ; 8000 est pris par Portainer) |
| `PROXMOX_*` | Endpoint Proxmox (un seul nœud suffit, tout le cluster est lu) |
| `CLOUDFLARE_*`, `NGINX_PROXY_HOSTS` | Plugin Cloudflare et détection du passage par Nginx |
| `SCAN_*` | Cibles, planification et profondeur du scan orb-agent |
| `CMDB_TOKEN_*` | Un token API NetBox par consommateur (orb-agent, agent Nginx, agents Docker, Zabbix, MCP en lecture seule), droits minimum |
| `ADGUARD_*` | Instances AdGuard Home et identifiants |
| `DOCKER_AGENT_HOST_NAME`, `DOCKER_AGENT_HOSTS` | Nom du LXC dans NetBox ; liste des hôtes Docker attendus (alerte Zabbix si l'un se tait) |
| `MCP_DEFAULT_PREFIX`, `MCP_RESERVED_IP_RANGES` | Préfixe par défaut et plages jamais proposées (DHCP) pour les IPs libres |
| `DIODE_CLIENT_SECRET_*` | Un client OAuth2 Diode par usage (`orb-agent`, `nginx-agent`, et les deux clients internes) |

## Mise à jour

- **Images** : dans Portainer, *Pull and redeploy* sur la stack. `latest` suit `main`, `dev` suit `dev`. Pour figer une version : `CMDB_IMAGE_TAG=1.2.3`.
- **Montée de version de NetBox** : sur `dev`, changer `ARG NETBOX_VERSION` dans `image/netbox/Dockerfile`, vérifier la compatibilité de chaque plugin (colonne `min_version`/`max_version` de leur `PluginConfig` ou leur README) et ajuster `image/netbox/plugin_requirements.txt`. Le CI vérifie que tous les plugins se chargent, que les migrations sont complètes et que les tests passent ; ne merger sur `main` que si le CI est vert et que l'image `dev` a tourné correctement.
- Les migrations sont appliquées automatiquement au démarrage.

## Ajouter un plugin

- **Plugin PyPI** : ajouter la ligne `paquet==version` dans `image/netbox/plugin_requirements.txt`, ajouter son nom dans `PLUGINS` et sa configuration dans `PLUGINS_CONFIG` de `image/netbox/config/plugins.py` (valeurs sensibles lues dans l'environnement), puis pousser. Mettre à jour `expected = 14` dans le workflow.
- **Plugin maison** : créer `plugins/<nom>/` (paquet Python avec `pyproject.toml`, README, licence MIT, tests dans `<module>/tests/`), l'ajouter à la commande `uv pip install` du `Dockerfile`, à `PLUGINS`, et à la commande `manage.py test` du workflow.

## Changer un secret

| Secret | Procédure |
| --- | --- |
| `DIODE_CLIENT_SECRET_*` | Changer la variable et redéployer la stack : `diode-bootstrap` met à jour le client dans Hydra à chaque démarrage. Reporter le nouveau secret dans `/etc/cmdb-nginx-agent.env` pour `nginx-agent`. |
| `CMDB_TOKEN_*` | Générer une valeur avec `python3 tools/generate-env.py --token`, changer la variable, redéployer : l'ancien token est supprimé et remplacé. Mettre à jour Zabbix / l'agent Nginx. |
| `PROXMOX_TOKEN_VALUE`, `CLOUDFLARE_API_TOKEN` | Changer la variable et redéployer : l'endpoint / la configuration sont relus au démarrage. |
| Mots de passe des bases (`NETBOX_DB_PASSWORD`, `DIODE_DB_PASSWORD`, `HYDRA_DB_PASSWORD`…) | Ils sont fixés à la création des volumes : changer d'abord le mot de passe dans PostgreSQL (`ALTER USER … PASSWORD …` via la console du conteneur), puis la variable, puis redéployer. |
| `NETBOX_SECRET_KEY` | Peut être changé à tout moment (déconnecte les sessions). |
| `NETBOX_API_TOKEN_PEPPER` | Le changer invalide tous les tokens API ; les tokens `svc-*` sont recréés au redémarrage, les autres sont à recréer. |
| `HYDRA_SECRETS_SYSTEM` | Le changer invalide les jetons OAuth2 en cours (renouvelés automatiquement). |

## Sécurité

- Accès local uniquement : la CMDB n'est jamais publiée dans le tunnel Cloudflare. `BIND_ADDRESS` permet de limiter l'écoute à l'interface LAN.
- Toute ingestion Diode est authentifiée par un client OAuth2 dédié (`orb-agent`, `nginx-agent`).
- Comptes : un admin nominatif ; des comptes `svc-*` sans mot de passe utilisable, un token chacun, avec la seule permission dont ils ont besoin.
- Aucun secret dans le dépôt ni dans les images : la configuration lit tout dans l'environnement ; le CI lance gitleaks sur tout l'historique Git.
- Sauvegarde : aucune en v1 (décision assumée). Les données vivent dans les volumes Docker `cmdb_*`.

## Développement

```bash
# tests de l'agent Nginx
pip install -e 'agents/nginx-agent[test]' && pytest agents/nginx-agent/tests
# image + tests des plugins (comme le CI) : voir .github/workflows/build.yml, job « test »
docker build -f image/netbox/Dockerfile -t netbox-cmdb:dev .
```

Branches : `main` (versions stables uniquement) et `dev` (le reste). Tags d'images : `latest` depuis `main`, `dev` depuis `dev`, version sémantique depuis un tag Git `vX.Y.Z`, et `sha-<commit>` pour chaque commit. Rebuild automatique chaque lundi.

## Phase 2 (hors v1)

Diff nmap déclaré / observé avec alerte Zabbix, et inventaire dynamique Ansible via la collection `netbox.netbox` (prévoir un compte `svc-ansible` en lecture seule, sur le modèle de `SERVICE_ACCOUNTS` dans `plugins/netbox-cmdb/netbox_cmdb/bootstrap.py`).

## Licence

MIT — voir [LICENSE](LICENSE).
