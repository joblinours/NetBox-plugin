# netbox-cmdb-mcp

Serveur **MCP** (Model Context Protocol) en lecture seule, servi par NetBox lui-même : Claude Code peut interroger la CMDB avant d'implémenter un projet (quelles machines, quelles IP et quels ports sont pris ou libres, quelles URL et quels noms DNS existent, quels conteneurs tournent où).

*Read-only MCP server served by NetBox (streamable HTTP, stateless, JSON responses).*

- Endpoint : `http://<cmdb>:10000/api/plugins/mcp/` (POST JSON-RPC, transport « streamable HTTP » sans session).
- Authentification : token API NetBox (`Authorization: Bearer nbt_…`). Chaque outil ne voit que ce que l'utilisateur du token a le droit de voir ; la stack crée `svc-mcp` (lecture seule) depuis `CMDB_TOKEN_MCP`.
- Accès local uniquement (LAN / ZeroTier), comme le reste de la CMDB.

## Brancher Claude Code

```bash
claude mcp add --transport http --scope user cmdb http://192.168.1.13:10000/api/plugins/mcp/ \
  --header "Authorization: Bearer <CMDB_TOKEN_MCP>"
```

Puis dans Claude Code : `/mcp` doit lister `cmdb` comme connecté.

## Outils

| Outil | Rôle |
| --- | --- |
| `cmdb_overview` | Clusters, nombre d'objets, état des sources automatiques |
| `search` | Recherche libre : hôtes, IPs, services, noms DNS, conteneurs |
| `list_hosts` / `get_host` | Hôtes (VM, LXC, équipements) ; fiche complète d'un hôte (IPs, services, ports, conteneurs, custom fields) |
| `list_used_ports` / `check_port` / `find_free_ports` | Ports utilisés sur un hôte (services NetBox, ports publiés Docker, scan réseau), test d'un port, ports libres dans une plage |
| `check_ip` / `find_free_ips` | IP utilisée ou non ; IPs inconnues de la CMDB dans un préfixe (hors passerelle, plages réservées, réécritures DNS) |
| `list_public_urls` / `list_dns_names` | URLs publiques Cloudflare (chemin d'exposition, service cible) ; noms locaux AdGuard et publics |
| `list_containers` | Conteneurs Docker (stack, image, état, ports, réseaux internes, volumes) |
| `export` | CMDB complète en Markdown, graphe Mermaid ou JSON |

Réglages (variables de la stack) : `MCP_DEFAULT_PREFIX` (préfixe par défaut de `find_free_ips`), `MCP_RESERVED_IP_RANGES` (ex. plage DHCP `192.168.1.100-192.168.1.199`, jamais proposée).

« Libre » veut dire « inconnu de la CMDB » : la donnée a la fraîcheur de la dernière synchronisation (quotidienne).

## Licence

MIT
