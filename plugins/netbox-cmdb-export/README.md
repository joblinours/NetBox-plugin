# netbox-cmdb-export

Export de la CMDB : **Markdown**, **PDF**, **JSON**, et **graphe topologique** en **Mermaid**, **PNG**, **SVG** ou DOT (Graphviz).

*Exports the CMDB as Markdown, PDF, JSON, or a topology graph (Mermaid, PNG, SVG, DOT).*

- UI : menu *Plugins > Export CMDB* (`/plugins/export/`), avec aperçu du graphe.
- Fichiers : `/plugins/export/cmdb.md`, `cmdb.pdf`, `cmdb.json`, `cmdb.mmd`, `cmdb.png`, `cmdb.svg`, `cmdb.dot`.
- API (token) : `GET /api/plugins/export/<format>/`, par ex. `curl -H "Authorization: Bearer $TOKEN" http://cmdb:8000/api/plugins/export/md/ -o cmdb.md`.
- `?containers=1` : un nœud par conteneur dans le graphe (sinon un nœud par stack).

Contenu : vue d'ensemble, clusters / nœuds / VMs, fiche par hôte (IPs, domaines locaux, ports utilisés et par qui, conteneurs), URLs publiques, noms DNS, hôtes Docker et réseaux internes. Graphe : cluster → nœud → VM/LXC, URL publique → (Nginx) → hôte, hôte Docker → stacks/conteneurs avec ports publiés.

Seuls les objets visibles par l'utilisateur sont exportés. Le PDF utilise la police DejaVu et le PNG/SVG le binaire `dot`, tous deux installés dans l'image NetBox de la CMDB.

## Licence

MIT
