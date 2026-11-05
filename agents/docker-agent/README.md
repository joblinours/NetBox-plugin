# cmdb-docker-agent

Agent qui lit l'API Docker de l'hôte en **lecture seule** (`/info`, `/containers/json?all=1`, `/containers/<id>/json`, `/networks`) et envoie un instantané complet au plugin `netbox-docker-inventory`. Bibliothèque standard Python uniquement. Image : `ghcr.io/joblinours/netbox-cmdb-docker-agent`.

*Reads the local Docker API (read-only) and pushes a full snapshot to NetBox every hour.*

## Sur l'hôte de la CMDB

Rien à faire : le service `docker-agent` fait partie de la stack CMDB. Régler `DOCKER_AGENT_HOST_NAME` sur le nom du LXC dans NetBox.

## Sur un autre hôte Docker

Dans Portainer, sur l'environnement de cet hôte : *Stacks > Add stack > Repository*, compose path `deploy/docker-agent.compose.yml`, variables :

| Variable | Valeur |
| --- | --- |
| `NETBOX_URL` | `http://192.168.1.13:8000` |
| `CMDB_TOKEN_DOCKER_AGENT` | même valeur que dans la stack CMDB |
| `DOCKER_AGENT_HOST_NAME` | nom de la VM dans NetBox |
| `DOCKER_AGENT_ADDRESSES` | IP de l'hôte (aide au rattachement) |

Puis ajouter ce nom à `DOCKER_AGENT_HOSTS` dans la stack CMDB, pour que Zabbix alerte si l'agent cesse de remonter.

Variables optionnelles : `DOCKER_AGENT_INTERVAL` (secondes, 3600 ; `0` = une seule exécution), `DOCKER_HOST` (par défaut `unix:///var/run/docker.sock`, accepte `tcp://` pour un docker-socket-proxy).

Test à blanc : `docker run --rm -v /var/run/docker.sock:/var/run/docker.sock:ro ghcr.io/joblinours/netbox-cmdb-docker-agent --dry-run --host-name test`.

> Le socket Docker est monté en lecture seule, mais l'accès au socket reste très puissant. Pour le restreindre aux lectures, placer un docker-socket-proxy (`CONTAINERS=1 NETWORKS=1 INFO=1`) devant et pointer `DOCKER_HOST` dessus.

## Licence

MIT
