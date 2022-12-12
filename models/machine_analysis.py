# -*- coding: utf-8 -*-
from datetime import datetime

from odoo import tools
from odoo import models, fields, api, _
from odoo.tools.safe_eval import pytz
from odoo.exceptions import UserError

class HrEmployee(models.Model):
    _inherit = 'hr.employee'

    device_id = fields.Char(string="ID biométrique de l'employé", )
    heur_travail_jour = fields.Float(string="Heurs de Travail par Jours")
    heur_arrive = fields.Float(string ="Heure d'arrivée", default=8.0)
    heur_depart = fields.Float(string="Heure de départ", default=17.3)
    tolerance = fields.Float(default=0.15)
    heur_arrive_tard = fields.Selection([('15', '15 munites'), ('30', '30 munites'), ('45', '45 munites'),
                                         ('1', '1 heure')], default='15')
    employee_absence_id = fields.One2many('employee.absence', 'employee_id', string="Employee Absence")
    make_invisible = fields.Boolean(string="Masquer label")
    heur_debut_pause = fields.Float(string="Heure de Début de Pause", default=12.30)
    heur_fin_pause = fields.Float(string="Heure de Fin de Pause", default=14.00)
    heur_de_travail = fields.Float(string="Nombre d'heure de travail par jour")
    heur_debut_pose = fields.Float(string="Heure de Début de Pause", default=12.00)
    heur_fin_pose = fields.Float(string="Heure de Fin de Pause", default=14.00)

    # Champ de tolerance de la pause
    tolerance_pause = fields.Float("Tolérence pause", default=0.1)


    jours_travailles_id = fields.Many2many('hr_attendance.jours_travailles',
                                           string="Jours travaillés")
    # Champs permettant de verifie si les jours travailles ont ete generes
    est_genere = fields.Boolean(default=False)

    @api.onchange('device_id')
    def _onchange_device_id(self):
        employees = self.env['hr.employee'].search([('device_id', '=', self.device_id), ('device_id', '!=', False)])
        # print("Les empl", employees)
        if employees:
            raise UserError("Désolé, cet id existe deja veuillez en choisir une autre !")

    def generer_jours_travailles(self):
        jts = self.env['hr_attendance.jours_travailles'].search([])
        jtl = [jt.id for jt in jts]
        employees = self.env['hr.employee'].search([])
        # if not jt and not self.est_genere:
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Lundi"})
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Mardi"})
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Mercredi"})
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Jeudi"})
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Vendredi"})
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Samedi"})
        #     self.env['hr_attendance.jours_travailles'].create({'jours_travailles': "Dimanche"})
        #     self.est_genere = True
        #
        # if self.est_genere:
        #     for emp in self.env['hr.employee'].search([]):
        #         emp.est_genere = True

        for employee in employees:
            employee.write({'jours_travailles_id': jtl[0:5]})

class JoursTravailles(models.Model):

    _name = "hr_attendance.jours_travailles"
    _rec_name = 'jours_travailles'

    jours_travailles = fields.Char(string="Jours travaillés")

class HrAbsence(models.Model):
    _name = 'hr.absence'

    employee_id = fields.Many2one('hr.employee', string='Employé')
    date_absence = fields.Date(string='Date')
    heur_perdu = fields.Float(string="Heure perdue")

class HrEmployeeAbsence(models.Model):
    _name = 'employee.absence'

    motif_absence = fields.Selection([('maladie', 'Maladie'), ('conge', 'Congé'), ('autre', 'Autre')], string="Motif de l'absence")
    date_debut_absence = fields.Date(string="Date de début", require=True)
    date_fin_absence = fields.Date(string="Date de fin", require=True)
    employee_id = fields.Many2one('hr.employee', ondelete='cascade', string="Employee")

class HrAnalyse(models.Model):
    _name = 'hr.analyse'
    employee_id = fields.Many2one('hr.employee', ondelete='cascade', string="Employee")
    heur_de_travail = fields.Float(string='Heure de travail')


class WeekDay(models.Model):
    _name = "week.day"

    days = fields.Char(string="Jours de travail")



class ZkMachine(models.Model):
    _name = 'zk.machine.attendance'
    _inherit = 'hr.attendance'

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """overriding the __check_validity function for employee attendance."""
        pass

    device_id = fields.Char(string="ID de l'appareil biométrique")
    punch_type = fields.Selection([('0', 'Entrée'),
                                   ('1', 'Sortie'),
                                   ('2', 'Pause'),
                                   ('3', 'Reprise pause'),
                                   ('4', 'Overtime In'),
                                   ('5', 'Overtime Out'),
                                   ('6', "Heure d'entrée modifiée"),
                                   ('7', "Heure de Sortie modifiée"),
                                   ('8', "Heure de Travail modifiée"),
                                   ('201', 'success'),
                                   ('255', 'error')
                                   ],
                                  string='Punching Type') #lié à date_modification.py

    attendance_type = fields.Selection([('1', 'Finger'),
                                        ('15', 'Face'),
                                        ('2','Type_2'),
                                        ('3','Password'),
                                        ('4','Card')], string='Category')
    punching_time = fields.Datetime(string='Sequence') #lié à date_modification.py
    address_id = fields.Many2one('res.partner', string='Adresse de travail')
    compare_date = fields.Date()
    compare = fields.Char()
    work_hours = fields.Float(string="Heures travaillées")
    mod_pers = fields.Char(string="Modification éffectuée par") #lié à date_modification.py
    # zk_report_daily_attendance_ids = fields.One2many('zk.report.daily.attendance', 'attendance_id')


class ReportZkDevice(models.Model):
    _name = 'zk.report.daily.attendance'
    _auto = False
    _order = 'punching_time desc'

    @api.model
    def _default_time_utc(self):
        locale_time = datetime.now()
        dt_utc = locale_time.astimezone(pytz.UTC)
        return dt_utc

    name = fields.Many2one('hr.employee', string='Employee')
    punching_day = fields.Datetime(string='Date')
    compare_date = fields.Date()
    compare = fields.Char()
    address_id = fields.Many2one(related='name.work_location_id', string='Lieu de travail')
    attendance_type = fields.Selection([('1', 'Finger'),
                                        ('15', 'Face'),
                                        ('2','Type_2'),
                                        ('3','Password'),
                                        ('4','Card')],
                                       string='Catégorie')
    punch_type = fields.Selection([('0', 'Pointage entrée'),
                                   ('1', 'Pointage sortie'),
                                   ('2', 'Pause'),
                                   ('3', 'Reprise pause'),
                                   ('4', 'Overtime In'),
                                   ('5', 'Overtime Out'),
                                   ('6', "Heure d'entrée modifiée"),
                                   ('7', "Heure de Sortie modifiée"),
                                   ('8', "Heure de Travail modifiée"),
                                   ('201', 'success'),
                                   ('255', 'error')], string='Type de Pointage')
    punching_time = fields.Datetime(string='Sequence')
    #date_registry = fields.Date(string='Date', default=_default_time_utc)
    work_hours = fields.Float(string="Heures travaillées", compute="_compute_hours")
    mod_pers = fields.Char(string="Modification éffectuée par")
    # attendance_id = fields.Many2one('hr.attendance', string='Id de la ligne de presence')

    def init(self):
        tools.drop_view_if_exists(self._cr, 'zk_report_daily_attendance')
        query = """
            create or replace view zk_report_daily_attendance as (
                select
                    min(z.id) as id,
                    z.employee_id as name,
                    z.write_date as punching_day,
                    z.address_id as address_id,
                    z.attendance_type as attendance_type,
                    z.punching_time as punching_time,
                    z.punch_type as punch_type,
                    z.compare_date as compare_date,
                    z.compare as compare,
                    z.work_hours as work_hours,
                    z.mod_pers as mod_pers
                from zk_machine_attendance z
                    join hr_employee e on (z.employee_id=e.id)
                GROUP BY
                    z.employee_id,
                    z.write_date,
                    z.address_id,
                    z.attendance_type,
                    z.punch_type,
                    z.punching_time,
                    z.compare,
                    z.compare_date,
                    z.work_hours,
                    z.mod_pers
            )
        """
        # print("Requete", query)
        self._cr.execute(query)

    def _compute_hours(self):
        zk_model_date = self.env["zk.report.daily.attendance"].search([]).mapped('punching_time')
        zk_model_name = self.env["zk.report.daily.attendance"].search([]).mapped('name')
        #print('zk_model_name= ', zk_model_name.name)
        n = len(zk_model_date)
        print(n)

        for log in self:

            if log.punch_type == '0':
                log.work_hours = 0

            else:
                log.work_hours = log.punching_time.hour - zk_model_date[n-2].hour
                print('log.work_hours', log.work_hours)
