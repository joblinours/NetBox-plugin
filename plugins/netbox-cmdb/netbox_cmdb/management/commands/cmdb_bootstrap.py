from django.core.management.base import BaseCommand

from netbox_cmdb import bootstrap


class Command(BaseCommand):
    help = "Provision the CMDB base data model, service accounts and Proxmox endpoint from the environment"

    def handle(self, *args, **options):
        self.stdout.write("CMDB bootstrap:")
        bootstrap.run(stdout=self.stdout)
        self.stdout.write(self.style.SUCCESS("CMDB bootstrap done"))
