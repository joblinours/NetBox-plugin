# netbox-docker-inventory

Inventaire Docker dans NetBox : **hôtes Docker, stacks (projets compose / Portainer), conteneurs — y compris ceux qui n'émettent aucun trafic —, réseaux internes de chaque stack, ports publiés et volumes**. Les données sont poussées par `cmdb-docker-agent` (dossier `agents/docker-agent`), qui tourne sur chaque hôte Docker.

*Docker hosts, compose stacks, containers (even silent ones), internal networks, published ports and volumes, pushed by an agent on each Docker host.*

- Modèles : `DockerHost` (rattaché à la VM / l'équipement NetBox par nom ou IP), `DockerNetwork` (driver, interne ou non, sous-réseaux, stack), `DockerContainer` (image, état, santé, stack, ports, réseaux et IP internes, volumes, labels compose).
- Pour chaque conteneur qui publie des ports, un `ipam.Service` est créé sur l'hôte avec le custom field **Stack Portainer** : les ports Docker apparaissent avec les autres services (et dans le MCP / l'export). Ces services sont supprimés avec le conteneur.
- API : `POST /api/plugins/docker-inventory/snapshot/` (agent, permissions add/change sur `dockerhost`) ; lecture : `/api/plugins/docker-inventory/{hosts,networks,containers}/`.
- Chaque instantané est enregistré comme source `docker-<hôte>` (Zabbix alerte si un agent se tait).

Idempotent : un instantané identique ne change rien ; les conteneurs et réseaux disparus sont supprimés.

## Licence

MIT
