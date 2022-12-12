from datetime import datetime
from time import gmtime, strftime
from odoo import api, models, fields


class DateModification(models.TransientModel):
    _name = "date.modification"

    @api.depends('choice')
    def _get_verif_presence(self):
        presence = self.env['hr.attendance'].search([('id', '=', self._context.get('active_id'))])
        print("Fonc exec", type(presence.statut))
        if presence.statut == 'absent':
            # print("Le if")
            return True
        else:
            return False
        # print("absence", self.absence)
    date_change_in = fields.Float(string="Arrivée réelle")
    date_change_out = fields.Float(string="Départ réel")
    hour_change = fields.Float(string="heures travaillées")
    mod_users = fields.Char("User ID", default=lambda self: self.env.user.name) #permets d'avoir l'utilisateur loggué
    date_modif = fields.Selection([('6', "Heure d'entrée modifiée"), ('7', 'Heure de Sortie modifiée'), ('8', "Heure de Travail modifiée")], default='6')

    choice = fields.Selection([('1', 'Modification heure arrivée réelle'), ('2', 'Modification heure de départ réelle')], string="Heure à modifier", default='1')

    heure_modif = datetime.utcnow() #permets d'afficher l'heure actuelle
    absence = fields.Boolean(default=_get_verif_presence)
    est_present = fields.Boolean(string="Présent", default=False)

    # fonction pour modifier les heures d'entrée
    def add_date_entre(self):
        print('Work entre')
        heure_modif = datetime.utcnow()
        print('heure_modif', heure_modif)
        self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
            'heure_entre': self.date_change_in
        })

        #récuperation de l'heure de sortie
        wizard_heure_sortie = self.env['hr.attendance'].browse(self.env.context.get('active_id')).heure_sortie
        print('wizard_heure_sortie =', wizard_heure_sortie)

        #calcul de la nouvelle heure travaillée
        wizard_worked_hour = wizard_heure_sortie - self.date_change_in
        print('wizard_worked_hour =', wizard_worked_hour)

        #intégration de la nouvelle heure calculée
        if self.est_present:
            self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
                'worked_hour': wizard_worked_hour,
                'statut': 'present'
            })
        else:
            self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
                'worked_hour': wizard_worked_hour
            })

        #recherche de l'employé dont les heures sont modifiées
        user = self.env['hr.attendance'].browse(self.env.context.get('active_id')).employee_id
        print('user :', user)

        self.date_modif = '6'
        print('Modification effectuée')
        self.env['zk.machine.attendance'].create({
            'punch_type': self.date_modif,
            'punching_time': heure_modif,
            'employee_id': user.id,
            'mod_pers': self.mod_users,

        })
        # self.env['zk.machine.attendance'].browse(self.env.context.get('active_id')).create({
        #     'punch_type': self.date_modif,
        #     'punching_time': heure_modif,
        #     'mod_pers': self.mod_users,
        # }).write({
        #     'employee_id': user
        # })

        print('self.date_modif_in', self.date_modif)


    # fonction pour modifier les heures de sorties
    def add_date_sortie(self):
        print('Work sortie')
        heure_modif = datetime.utcnow()
        # heure_modif = datetime.strftime(fields.Datetime.context_timestamp(self, datetime.now()), "%Y-%m-%d %H:%M:%S")
        print('heure_modif', heure_modif)
        if self.est_present:
            self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
                'heure_sortie': self.date_change_out,
                'statut': 'present'
            })
        else:
            self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
                'heure_sortie': self.date_change_out
            })

        # récuperation de l'heure d'entrée
        wizard_heure_entre = self.env['hr.attendance'].browse(self.env.context.get('active_id')).heure_entre
        print('wizard_heure_entre =', wizard_heure_entre)

        # calcul de la nouvelle heure travaillée
        wizard_worked_hour = self.date_change_out - wizard_heure_entre
        print('wizard_worked_hour =', wizard_worked_hour)

        #intégration de la nouvelle heure calculée
        self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
            'worked_hour': wizard_worked_hour
        })

        #recherche de l'employé dont les heures sont modifiées
        user = self.env['hr.attendance'].browse(self.env.context.get('active_id')).employee_id
        print('user :', user)

        self.date_modif = '7'
        print('Modification effectuée')
        self.env['zk.machine.attendance'].create({
            'punch_type': self.date_modif,
            'punching_time': heure_modif,
            'mod_pers': self.mod_users,
            'employee_id': user.id
        })
        # self.env['zk.machine.attendance'].browse(self.env.context.get('active_id')).create({
        #     'punch_type': self.date_modif,
        #     'punching_time': heure_modif,
        #     'mod_pers': self.mod_users,
        # }).write({
        #     'employee_id': user
        # })
        print('self.date_modif_out', self.date_modif)


    # fonction pour modifier les heures travaillées
    def add_heure_travailler(self):
        print('Work heure travailler')
        heure_modif = datetime.utcnow()
        # heure_modif = datetime.strftime(fields.Datetime.context_timestamp(self, datetime.now()), "%Y-%m-%d %H:%M:%S")
        print('heure_modif', heure_modif)
        self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
            'worked_hour': self.hour_change
        })

        # récuperation de l'heure d'entrée
        wizard_heure_entre = self.env['hr.attendance'].browse(self.env.context.get('active_id')).heure_entre
        print('wizard_heure_entre =', wizard_heure_entre)

        # calcul de la nouvelle heure de sortie
        wizard_heure_sortie = self.hour_change + wizard_heure_entre
        print('wizard_heure_sortie =', wizard_heure_sortie)

        # intégration de la nouvelle heure de sortie
        self.env['hr.attendance'].browse(self.env.context.get('active_id')).write({
            'heure_sortie': wizard_heure_sortie
        })

        #recherche de l'employé dont les heures sont modifiées
        user = self.env['hr.attendance'].browse(self.env.context.get('active_id')).employee_id
        print('user :', user)

        self.date_modif = '8'
        print('Modification effectuée')
        # self.env['zk.machine.attendance'].browse(self.env.context.get('active_id')).write({
        #     'punch_type': self.date_modif,
        #     'punching_time': heure_modif,
        #     'mod_pers': self.mod_users,
        #     'employee_id': user
        # })
        self.env['zk.machine.attendance'].browse(self.env.context.get('active_id')).create({
            'punch_type': self.date_modif,
            'punching_time': heure_modif,
            'mod_pers': self.mod_users,
        }).write({
            'employee_id': user
        })
        print('Modification effectuée', self.date_modif)

