# -*- coding: utf-8 -*-

from . import models
from . import wizard
from . import report
from odoo import api, SUPERUSER_ID


def initialize_heure_travailles(env):

    valeur = False
    # la variable valeur doit etre True lorsque la fonctionnalité heure travaillée sera utilisée.
    env['heure.travaillees'].create({
        'is_heure_travaillees': valeur
    })
    print("Creation de heure travaillees reussi.")

def _post_init_hook(cr, registry):
    env = api.Environment(cr, SUPERUSER_ID, {})
    if not env['heure.travaillees'].search([]):
        initialize_heure_travailles(env)