# netbox-adguard

Importe les **réécritures DNS d'AdGuard Home** (noms de domaine locaux) dans NetBox.

*Imports AdGuard Home DNS rewrites into NetBox and mirrors them into netbox-plugin-dns.*

Pour chaque réécriture (`GET /control/rewrite/list` de chaque instance) :

1. un objet *DNS rewrite* (domaine → réponse), rattaché à l'IP NetBox et à l'hôte (VM / équipement) visé, en suivant les CNAME ;
2. le custom field **Domaines locaux** (`local_domains`) de cette IP et de cet hôte liste ses noms locaux ;
3. un enregistrement **A / AAAA / CNAME** dans netbox-plugin-dns (zone existante la plus longue qui correspond, sinon zone parente créée), tagué `adguard`.

Idempotent ; les réécritures supprimées disparaissent (seulement pour les instances qui ont répondu : une panne d'AdGuard n'efface rien). Les réécritures désactivées sont gardées mais pas publiées en DNS. Job système quotidien, bouton *Sync now*, statut remonté comme source `adguard` (Zabbix).

## Configuration (variables de la stack)

| Variable | Rôle |
| --- | --- |
| `ADGUARD_URLS` | URL(s) d'AdGuard Home, séparées par des virgules (ex. `http://192.168.1.2:3000`) |
| `ADGUARD_USERNAME` / `ADGUARD_PASSWORD` | Compte AdGuard (mêmes identifiants pour toutes les instances) |
| `ADGUARD_VERIFY_SSL` | `true` par défaut |
| `ADGUARD_SYNC_INTERVAL` | minutes (1440) |
| `ADGUARD_SYNC_NETBOX_DNS`, `ADGUARD_AUTO_CREATE_ZONES` | Miroir vers netbox-plugin-dns, création des zones |

AdGuard Home n'a pas de compte en lecture seule : créer un utilisateur dédié dans `AdGuardHome.yaml` (section `users`) et le ranger dans Vaultwarden.

## Licence

MIT
