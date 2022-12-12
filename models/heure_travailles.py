from odoo import fields, api, models, _


class HeureTravaillees(models.Model):
    _name = "heure.travaillees"

    is_heure_travaillees = fields.Boolean("Activer la fonctionnalité heure travaillées?")