# SPDX-FileCopyrightText: 2024 Magenta ApS <info@magenta.dk>
#
# SPDX-License-Identifier: MPL-2.0

from django.db import models


class ESkatMandtal(models.Model):
    class Meta:
        managed = False  # Created from a view in a remote database. Don't remove.
        db_table = "eskat_mandtal"

    pt_census_guid = models.UUIDField(primary_key=True)
    cpr = models.TextField()
    # bank_reg_nr = models.TextField(blank=True, null=True)
    # bank_konto_nr = models.TextField(blank=True, null=True)
    kommune_no = models.IntegerField(blank=True, null=True)
    kommune = models.TextField(blank=True, null=True)
    skatteaar = models.IntegerField()
    navn = models.TextField(blank=True, null=True)
    adresselinje1 = models.TextField(blank=True, null=True)
    adresselinje2 = models.TextField(blank=True, null=True)
    adresselinje3 = models.TextField(blank=True, null=True)
    adresselinje4 = models.TextField(blank=True, null=True)
    adresselinje5 = models.TextField(blank=True, null=True)
    fuld_adresse = models.TextField(blank=True, null=True)
    # cpr_dashed = models.TextField(blank=True, null=True)
    skatteomfang = models.TextField(blank=True, null=True)
    skattedage = models.IntegerField(blank=True, null=True)

    @property
    def fully_tax_liable(self) -> bool:
        return (
            self.skatteomfang is not None
            and self.skatteomfang.lower() == "fuld skattepligtig"
        )
