# -*- coding: utf-8 -*-
from odoo.tools import format_datetime
from odoo import exceptions
from datetime import timedelta
import datetime
import logging
from struct import unpack

import pytz

from odoo import _
from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError
from .zkconst import *
from datetime import time
# from datetime import datetime as time

_logger = logging.getLogger(__name__)
try:
    from zk import ZK, const
except ImportError:
    _logger.error("Veuillez installer la bibliothèque pyzk.")

_logger = logging.getLogger(__name__)


class HrLeaveInherit(models.Model):
    _inherit = 'hr.leave'

    def _onchange_state(self):
        if self.state == 'validate':

            date_debut = self.date_from.date()
            date_fin = self.date_to.date()

            l = []
            jours_travailles = self.env['hr.employee'].search([('id', '=', self.employee_id.id)]).mapped(
                'jours_travailles_id')
            for jt in jours_travailles:
                if jt.jours_travailles == 'Lundi':
                    l.append(0)
                elif jt.jours_travailles == 'Mardi':
                    l.append(1)
                elif jt.jours_travailles == 'Mercredi':
                    l.append(2)
                elif jt.jours_travailles == 'Jeudi':
                    l.append(3)
                elif jt.jours_travailles == 'Vendredi':
                    l.append(4)
                elif jt.jours_travailles == 'Samedi':
                    l.append(5)
                elif jt.jours_travailles == 'Dimanche':
                    l.append(6)

            presences = self.env['hr.attendance'].search([
                ('employee_id', '=', self.employee_id.id),
                ('date_pointage', '>=', date_debut),
                ('date_pointage', '<=', date_fin),
            ])

            presences.filtered(lambda self: self.statut == 'absent')

            for presence in presences:
                if presence.date_pointage.weekday() in l:
                    presence.statut = 'conge'

    def action_validate(self):
        current_employee = self.env.user.employee_id
        leaves = self._get_leaves_on_public_holiday()
        if leaves:
            raise ValidationError(
                _('The following employees are not supposed to work during that period:\n %s') % ','.join(
                    leaves.mapped('employee_id.name')))

        if any(holiday.state not in ['confirm', 'validate1'] and holiday.validation_type != 'no_validation' for holiday
               in self):
            raise UserError(_('Time off request must be confirmed in order to approve it.'))

        self.write({'state': 'validate'})
        self._onchange_state()
        leaves_second_approver = self.env['hr.leave']
        leaves_first_approver = self.env['hr.leave']

        for leave in self:
            if leave.validation_type == 'both':
                leaves_second_approver += leave
            else:
                leaves_first_approver += leave

            if leave.holiday_type != 'employee' or \
                    (leave.holiday_type == 'employee' and len(leave.employee_ids) > 1):
                if leave.holiday_type == 'employee':
                    employees = leave.employee_ids
                elif leave.holiday_type == 'category':
                    employees = leave.category_id.employee_ids
                elif leave.holiday_type == 'company':
                    employees = self.env['hr.employee'].search([('company_id', '=', leave.mode_company_id.id)])
                else:
                    employees = leave.department_id.member_ids

                conflicting_leaves = self.env['hr.leave'].with_context(
                    tracking_disable=True,
                    mail_activity_automation_skip=True,
                    leave_fast_create=True
                ).search([
                    ('date_from', '<=', leave.date_to),
                    ('date_to', '>', leave.date_from),
                    ('state', 'not in', ['cancel', 'refuse']),
                    ('holiday_type', '=', 'employee'),
                    ('employee_id', 'in', employees.ids)])

                if conflicting_leaves:
                    # YTI: More complex use cases could be managed in master
                    if leave.leave_type_request_unit != 'day' or any(
                            l.leave_type_request_unit == 'hour' for l in conflicting_leaves):
                        raise ValidationError(_('You can not have 2 time off that overlaps on the same day.'))

                    # keep track of conflicting leaves states before refusal
                    target_states = {l.id: l.state for l in conflicting_leaves}
                    conflicting_leaves.action_refuse()
                    split_leaves_vals = []
                    for conflicting_leave in conflicting_leaves:
                        if conflicting_leave.leave_type_request_unit == 'half_day' and conflicting_leave.request_unit_half:
                            continue

                        # Leaves in days
                        if conflicting_leave.date_from < leave.date_from:
                            before_leave_vals = conflicting_leave.copy_data({
                                'date_from': conflicting_leave.date_from.date(),
                                'date_to': leave.date_from.date() + timedelta(days=-1),
                                'state': target_states[conflicting_leave.id],
                            })[0]
                            before_leave = self.env['hr.leave'].new(before_leave_vals)
                            before_leave._compute_date_from_to()

                            # Could happen for part-time contract, that time off is not necessary
                            # anymore.
                            # Imagine you work on monday-wednesday-friday only.
                            # You take a time off on friday.
                            # We create a company time off on friday.
                            # By looking at the last attendance before the company time off
                            # start date to compute the date_to, you would have a date_from > date_to.
                            # Just don't create the leave at that time. That's the reason why we use
                            # new instead of create. As the leave is not actually created yet, the sql
                            # constraint didn't check date_from < date_to yet.
                            if before_leave.date_from < before_leave.date_to:
                                split_leaves_vals.append(before_leave._convert_to_write(before_leave._cache))
                        if conflicting_leave.date_to > leave.date_to:
                            after_leave_vals = conflicting_leave.copy_data({
                                'date_from': leave.date_to.date() + timedelta(days=1),
                                'date_to': conflicting_leave.date_to.date(),
                                'state': target_states[conflicting_leave.id],
                            })[0]
                            after_leave = self.env['hr.leave'].new(after_leave_vals)
                            after_leave._compute_date_from_to()
                            # Could happen for part-time contract, that time off is not necessary
                            # anymore.
                            if after_leave.date_from < after_leave.date_to:
                                split_leaves_vals.append(after_leave._convert_to_write(after_leave._cache))

                    split_leaves = self.env['hr.leave'].with_context(
                        tracking_disable=True,
                        mail_activity_automation_skip=True,
                        leave_fast_create=True,
                        leave_skip_state_check=True
                    ).create(split_leaves_vals)

                    split_leaves.filtered(lambda l: l.state in 'validate')._validate_leave_request()

                values = leave._prepare_employees_holiday_values(employees)
                leaves = self.env['hr.leave'].with_context(
                    tracking_disable=True,
                    mail_activity_automation_skip=True,
                    leave_fast_create=True,
                    no_calendar_sync=True,
                    leave_skip_state_check=True,
                ).create(values)

                leaves._validate_leave_request()

        leaves_second_approver.write({'second_approver_id': current_employee.id})
        leaves_first_approver.write({'first_approver_id': current_employee.id})

        employee_requests = self.filtered(lambda hol: hol.holiday_type == 'employee')
        employee_requests._validate_leave_request()
        if not self.env.context.get('leave_fast_create'):
            employee_requests.filtered(lambda holiday: holiday.validation_type != 'no_validation').activity_update()
        return True


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'
    _order = "date_pointage desc"


    def _hr_attendance_action(self):

        action = {
            'name': 'Pointages',
            'type': 'ir.actions.act_window',
            'res_model': 'hr.attendance',
            'view_mode': 'tree,kanban,form',
            'context': {'search_default_date_two_week': 1, 'search_default_date': 1, 'search_default_today': 1},
            # 'domain': [('is_work_day', '=', 1)],
            # 'views': [(self.env.ref('progistack_attendance.inherited_view_attendance_tree').id, 'tree'), [False, 'kanban'], [False, 'form']],
            'search_view_id': self.env.ref('hr_attendance.hr_attendance_view_filter').id,
            'help': """
                        <p class="o_view_nocontent_empty_folder">
                            Aucun enregistrement de présence trouvé
                        </p>
                        <p>
                            Les registres de présence de vos employés seront affichés ici.
                        </p>
                    """
        }
        # print("Heure trava", self, self._context)
        heure_travaillees = self.env['heure.travaillees'].search([], limit=1)
        domain = [('is_work_day', '=', True)]
        if heure_travaillees:
            # attendance = self.env['hr.attendance'].search([], limit=1)
            if heure_travaillees.is_heure_travaillees:
                for s in self.sudo().search([]):
                    s._is_work_hour_use = 1
                # print("Le if", self)
            else:
                for s in self.sudo().search([]):
                    s._is_work_hour_use = 0
                # action['views'][0] = (self.env.ref('progistack_attendance.inherited_view_attendance_tree').id, 'tree')
        action['domain'] = domain
        return action
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            l = []
            jours_travailles = self.env['hr.employee'].search([('id', '=', vals.get('employee_id'))]).mapped(
                'jours_travailles_id')
            for jt in jours_travailles:
                if jt.jours_travailles == 'Lundi':
                    l.append(0)
                elif jt.jours_travailles == 'Mardi':
                    l.append(1)
                elif jt.jours_travailles == 'Mercredi':
                    l.append(2)
                elif jt.jours_travailles == 'Jeudi':
                    l.append(3)
                elif jt.jours_travailles == 'Vendredi':
                    l.append(4)
                elif jt.jours_travailles == 'Samedi':
                    l.append(5)
                elif jt.jours_travailles == 'Dimanche':
                    l.append(6)
            if vals.get('date_pointage'):
                work_date = None
                if isinstance(vals.get('date_pointage'), datetime):
                    work_date = vals.get('date_pointage').date()
                else:
                    work_date = datetime.strptime(str(vals.get('date_pointage')), '%Y-%m-%d')
                if work_date.weekday() in l:
                    vals['is_work_day'] = True
                else:
                    vals['is_work_day'] = False
            res = super().create(vals)
            res._update_overtime()
        return res

    def _set_statut(self):
        heure_travaillees = self.env['heure.travaillees'].search([])
        print("heure_travaillees", heure_travaillees.is_heure_travaillees)
        for s in self:
            if heure_travaillees.is_heure_travaillees:
                anticipe = False
                retard = False
                # Les pointages entrees
                zk_entree = self.env['zk.machine.attendance'].search([
                    ('punch_type', '=', '0'),
                    ('employee_id', '=', s.employee_id.id)
                ])
                zk_entree = zk_entree.filtered(lambda sf: sf.punching_time.date() == s.date_pointage)
                # Les pointages sorties
                zk_sortie = self.env['zk.machine.attendance'].search([
                    ('punch_type', '=', '1'),
                    ('employee_id', '=', s.employee_id.id)
                ])
                zk_sortie = zk_sortie.filtered(lambda sf: sf.punching_time.date() == s.date_pointage)
                taille_entree = len([zk.id for zk in zk_entree])
                taille_sortie = len([zk.id for zk in zk_sortie])
                # print("Taille ent et sortie", taille_entree, taille_sortie)
                if s.heur_planifie + s.tolerance >= s.heure_entre:
                    # print("1er if", s.employee_id.name)
                    s.statut = 'present'
                    s.etat = 'present'

                if s.heur_planifie + s.tolerance < s.heure_entre:
                    s.statut = 'retard'
                    s.etat = 'retard'
                    retard = True
                if s.heur_depart - s.tolerance > s.heure_sortie:
                    # print("Le statut est anticipe")
                    s.statut = 'anticipe'
                    s.etat = 'anticipe'
                    anticipe = True
                if taille_entree != taille_sortie and s.date_pointage != fields.Date.today():
                    s.statut = 'erreur'
                    s.etat = 'erreur'
                    continue
                if s.heure_entre == 0:
                    hr_leave = s.env['hr.leave'].search(
                        [('state', '=', 'validate'), ('employee_id', '=', s.employee_id.id)])
                    if hr_leave:
                        s.statut = 'conge'
                        s.etat = 'congé'
                    else:
                        s.statut = 'absent'
                        s.etat = 'absent'
                    continue
                    # print("Anticipe et retard", anticipe, retard)
                if anticipe and retard:
                    s.statut = 'retard_anticipe'
                    s.etat = 'retard_anticipe'
            else:
                anticipe = False
                retard = False
                # Les pointages entrees
                zk_entree = self.env['zk.machine.attendance'].search([
                    ('punch_type', '=', '0'),
                    ('employee_id', '=', s.employee_id.id)
                ])
                zk_entree = zk_entree.filtered(lambda sf: sf.punching_time.date() == s.date_pointage)
                # Les pointages sorties
                zk_sortie = self.env['zk.machine.attendance'].search([
                    ('punch_type', '=', '1'),
                    ('employee_id', '=', s.employee_id.id)
                ])
                zk_sortie = zk_sortie.filtered(lambda sf: sf.punching_time.date() == s.date_pointage)
                entrees = [zk.id for zk in zk_entree]
                sorties = [zk.id for zk in zk_sortie]
                # print("Taille ent et sortie", taille_entree, taille_sortie)
                if s.heur_planifie + s.tolerance >= s.heure_entre:
                    # print("1er if", s.employee_id.name)
                    s.statut = 'present'
                    s.etat = 'present'

                if s.heur_planifie + s.tolerance < s.heure_entre:
                    s.statut = 'retard'
                    s.etat = 'retard'
                    retard = True
                if s.heur_depart - s.tolerance > s.heure_sortie:
                    # print("Le statut est anticipe")
                    s.statut = 'anticipe'
                    s.etat = 'anticipe'
                    anticipe = True
                if (entrees and not sorties) or (not entrees and sorties):
                    s.statut = 'erreur'
                    s.etat = 'erreur'
                    # print(f"Statut de {s.employee_id.name}: {s.statut}")
                    continue
                if s.heure_entre == 0:
                    hr_leave = s.env['hr.leave'].search(
                        [('state', '=', 'validate'), ('employee_id', '=', s.employee_id.id)])
                    if hr_leave:
                        s.statut = 'conge'
                        s.etat = 'congé'
                    elif s.heure_sortie == 0:
                        s.statut = 'absent'
                        s.etat = 'absent'
                    # print(f"Statut de {s.employee_id.name}: {s.statut}")
                    continue
                    # print("Anticipe et retard", anticipe, retard)
                if anticipe and retard:
                    s.statut = 'retard_anticipe'
                    s.etat = 'retard_anticipe'
                # print(f"Statut de {s.employee_id.name}: {s.statut}")

    def set_break(self):
        for s in self:
            print("empl", s.employee_id.name)
            # Heure debut et fin de pause
            hdp = s.employee_id.heur_debut_pause
            # print(int(hdp), int(str(hdp).split('.')[1]), s.employee_id.tolerance_pause)
            hdp_min = float('{0:02.0f}.{1:02.0f}'.format(*divmod((int(hdp)*60 + int(str(str(hdp)+'0').split('.')[1]) - s.employee_id.tolerance_pause*100), 60)))
            hdp_max = float('{0:02.0f}.{1:02.0f}'.format(*divmod((int(hdp)*60 + int(str(str(hdp)+'0').split('.')[1]) + s.employee_id.tolerance_pause*100), 60)))

            hfp = s.employee_id.heur_fin_pause
            hfp_min = float('{0:02.0f}.{1:02.0f}'.format(*divmod((int(hfp)*60 + int(str(str(hfp)+'0').split('.')[1]) - s.employee_id.tolerance_pause*100), 60)))
            hfp_max = float('{0:02.0f}.{1:02.0f}'.format(*divmod((int(hfp)*60 + int(str(str(hfp)+'0').split('.')[1]) + s.employee_id.tolerance_pause*100), 60)))

            # Les pointages entrees
            zk_entree = self.env['zk.machine.attendance'].search([
                ('punch_type', '=', '0'),
                ('employee_id', '=', s.employee_id.id)
            ])
            zk_entree = zk_entree.filtered(lambda sf: sf.punching_time.date() == s.date_pointage)

            # Les pointages sorties
            zk_sortie = self.env['zk.machine.attendance'].search([
                ('punch_type', '=', '1'),
                ('employee_id', '=', s.employee_id.id)
            ])
            zk_sortie = zk_sortie.filtered(lambda sf: sf.punching_time.date() == s.date_pointage)

            # Recuperation des heures de prises de pause
            # L'heure de prise de pause est la derniere periode de sortie inclus dans heur_debut_pause +/- tolerance
            # L'heure de reprise de pause est la premiere periode d'entree inclus dans heur_debut_pause +/- tolerance
            heures_entree = []
            for zk in zk_entree:
                if zk.punching_time:
                    punching_time = float("{}.{}".format(zk.punching_time.time().hour, zk.punching_time.time().minute))
                    print("Punching_time entree", punching_time)
                    if hdp_min < punching_time < hdp_max:
                        # prise = zk.punching_time.time()
                        heures_entree.append(punching_time)
                        print("Dans la cond entree", heures_entree)

            heures_sortie = []
            for zk in zk_sortie:
                if zk.punching_time:
                    punching_time = float("{}.{}".format(zk.punching_time.time().hour, zk.punching_time.time().minute))
                    print("Punching_time sortie", punching_time)
                    if hfp_min < punching_time < hfp_max:
                        # prise = zk.punching_time.time()
                        heures_sortie.append(punching_time)
                        print("Dans la cond sortie", heures_sortie)

            prise_pause = max(heures_entree) if heures_entree else False
            reprise_pause = min(heures_sortie) if heures_sortie else False

            print("PP et RP", prise_pause, reprise_pause)
            # La pause est respectée lorsqu'elle est prise entre
            if prise_pause and reprise_pause:
                if hdp_min < prise_pause < hdp_max and hfp_min < reprise_pause < hfp_max:
                    s._is_break_on_time = 'respected'
                    s._track_break_on_time = 'respected'
                else:
                    s._is_break_on_time = 'not_respected'
                    s._track_break_on_time = 'not_respected'
            else:
                s._is_break_on_time = 'not_respected'
                s._track_break_on_time = 'not_respected'


    def oder_numbers(self):
        order = 0
        for s in self:
            if s.statut == "absent":
                order = 0
            elif s.statut == "retard":
                order = 1
            elif s.statut == "retard_anticipe":
                order = 2
            elif s.statut == "conge":
                order = 3
            elif s.statut == "anticipe":
                order = 4
            elif s.statut == "erreur":
                order = 5
            s.order_number = order
            # print("is_wk est exec", s.is_work_day)

    device_id = fields.Char(string="ID biométrique de l'employé")
    absence_non_prevu = fields.Date(string="Absence")
    heur_planifie = fields.Float(string="Arrivée planifiée",
                                 group_operator=False)  # permets d'enlever le calcul fait par groupby
    heur_sup_jour = fields.Float(string="Heurs Supplementaire")
    tolerance = fields.Float()
    heur_depart = fields.Float(string="Départ planifié", group_operator=False)
    pointge_oublie = fields.Boolean(string="Pointage oublié")
    status = fields.Selection([('retard', 'Retard'), ('pile', "A l'heure")], string=" ")
    worked_hour = fields.Float(string="heures travaillées", compute="_compute_worked_hours", invert="",
                               store=True)  # store=True
    worked_minute = fields.Float(string="minutes travaillées", compute="_compute_worked_hours")
    date_pointage = fields.Date(string="Date")
    heure_entre = fields.Float(string="arrivée réelle", group_operator=False)
    # heure_entre = fields.Float(string="arrivée réelle", compute="_compute_heure_entre", invert="", group_operator=False)
    heure_sortie = fields.Float(string="Départ réel", group_operator=False)
    # heure_sortie = fields.Float(string="Départ réel", compute="_compute_heure_sortie", invert="", group_operator=False)
    visible = fields.Boolean(string="Visible")
    is_check = fields.Boolean(string='Déja pointé', default=False)
    sequence = fields.Integer(string="Sequence")
    statut = fields.Selection([
        ('conge', "En congé"),
        ('absent', "Absent"),
        ('retard', "En retard"),
        ('present', "Présent"),
        ('erreur', "Erreur"),
        ('anticipe', "Anticipé"),
        ('retard_anticipe', "Retard et Anticipé"),
    ], compute='_set_statut', string='statut')
    etat = fields.Char()
    is_work_day = fields.Boolean()
    order_number = fields.Integer(compute='oder_numbers')
    # Champ pour activer la fonctionnalité de heure travaillees.
    _is_work_hour_use = fields.Boolean("heure ttt")
    # Champ permettant de signifier le contexte de la prise de la pause.
    _is_break_on_time = fields.Selection([
        ('respected', "Heure de pause respectée"),
        ('not_respected', "Heure de pause non respectée"),
        ('no_again', "Pause pas encore prise"),
        ], compute='set_break', string="Pause")

    _track_break_on_time = fields.Char("Statut pause")

    def print_wizard(self):
        return {
            'type': 'ir.actions.act_window',
            'name': "Rapport de présence",
            'res_model': 'report.presence',
            'view_mode': 'form',
            'target': 'new',
        }

    def open_user_log(self):
        d1 = [('name', '=', str(self.employee_id.name)), ('compare_date', '=', self.date_pointage)]
        # d2 = [('name', '=', str(self.employee_id.name)), ('punch_type', 'in', ('6', '7'))]
        # domain = ['|', '&', d1[0], d1[1], '&', d2[0], d2[1]]
        domain = d1

        return {
            'type': 'ir.actions.act_window',
            'name': 'Détails',
            'view_mode': 'tree',
            'search_view_id ': 'action_zk_report_daily_attendance',
            'target': 'new',
            'res_model': 'zk.report.daily.attendance',
            'domain': domain
        }

    @api.onchange('employee_id')
    def onchange_employee_id(self):
        raise UserError(_("Vous essayez de changer l'employé."))

    @api.depends('heure_entre', 'heure_sortie')
    def set_statut(self):

        attendances = self.env['hr.attendance'].search([])
        for attendance in attendances:
            # Edition de statut
            if attendance.heur_planifie >= attendance.heure_entre or attendance.heur_planifie + attendance.tolerance >= attendance.heure_entre:
                attendance.statut = 'present'

            elif attendance.heur_planifie + attendance.tolerance < attendance.heure_entre:
                attendance.statut = 'retard'

            if not attendance.heure_entre or attendance.heure_entre == 0:
                hr_leave = self.env['hr.leave'].search(
                    [('state', '=', 'validate'), ('employee_id', '=', attendance.employee_id.id)])

                if hr_leave:
                    attendance.statut = 'conge'

                else:
                    attendance.statut = 'absent'

    @api.depends('heure_entre', 'heure_sortie', 'employee_id')
    def _compute_worked_hours(self):

        for attendance in self:

            if attendance.heure_entre and attendance.heure_sortie:
                if attendance.worked_hour > 8:
                    attendance.heur_sup_jour = attendance.worked_hour - 8
                else:
                    attendance.heur_sup_jour = 0.0
                zk_model_date_entree = self.env["zk.report.daily.attendance"].search(
                    [('punch_type', '=', '0'), ('name', '=', attendance.employee_id.name),
                     ('compare_date', '=', attendance.date_pointage)]).mapped('punching_time')
                # print("date entree zk",zk_model_date_entree)
                zk_model_date_sortie = self.env["zk.report.daily.attendance"].search(
                    [('punch_type', '=', '1'), ('name', '=', attendance.employee_id.name),
                     ('compare_date', '=', attendance.date_pointage)]).mapped('punching_time')
                # print("zk date sortie",zk_model_date_sortie)
                E = len(zk_model_date_entree)
                S = len(zk_model_date_sortie)
                # print("Entree et sortie", E, S)

                if E == 1 and S == 1:

                    if zk_model_date_entree[0] < zk_model_date_sortie[0]:
                        # attendance.worked_hour = zk_model_date_sortie[0].hour - zk_model_date_entree[0].hour + (
                        #         (zk_model_date_sortie[0].minute - zk_model_date_entree[0].minute) / 60)
                        attendance.worked_hour = zk_model_date_sortie[0].hour - zk_model_date_entree[0].hour
                        if zk_model_date_entree[0].minute < zk_model_date_sortie[0].minute:
                            attendance.worked_hour += (zk_model_date_sortie[0].minute - zk_model_date_entree[
                                0].minute) / 60
                        else:
                            attendance.worked_hour += -1 + (
                                    60 + zk_model_date_sortie[0].minute - zk_model_date_entree[0].minute) / 60
                    else:
                        # print("Cet idiot a printer sortie avant entree")
                        attendance.worked_hour = None

                elif E == S:
                    attendance.worked_hour = 0
                    # L'indice 0 doit etre inclus
                    for x in range(E):
                        if attendance.worked_hour == 0:
                            if zk_model_date_entree[x] < zk_model_date_sortie[x]:
                                attendance.worked_hour = zk_model_date_sortie[x].hour - zk_model_date_entree[x].hour
                                if zk_model_date_entree[x].minute < zk_model_date_sortie[x].minute:
                                    attendance.worked_hour += (zk_model_date_sortie[x].minute - zk_model_date_entree[
                                        x].minute) / 60
                                else:
                                    attendance.worked_hour += -1 + (
                                            60 + zk_model_date_sortie[x].minute - zk_model_date_entree[
                                        x].minute) / 60
                            else:
                                attendance.worked_hour = None
                                break
                        else:
                            attendance.worked_hour += zk_model_date_sortie[x].hour - zk_model_date_entree[x].hour
                            if zk_model_date_entree[x].minute < zk_model_date_sortie[x].minute:
                                attendance.worked_hour += (zk_model_date_sortie[x].minute - zk_model_date_entree[
                                    x].minute) / 60
                            else:
                                attendance.worked_hour += -1 + (
                                        60 + zk_model_date_sortie[x].minute - zk_model_date_entree[x].minute) / 60

                elif E > S:

                    attendance.worked_hour = False
                elif E < S:
                    attendance.worked_hour = False

            else:
                attendance.worked_hour = False

    def get_total_hours(self):
        self.ensure_one()
        action = {'type': 'ir.actions.act_window', 'view_mode': 'form', 'name': _('Modifications de la date de sortie'),
                  'res_model': 'hr.attendance', 'view_id': self.env.ref('progistack_attendance.view_modifie_date').id}

        return action

    @api.constrains('check_in', 'check_out', 'employee_id')
    def _check_validity(self):
        """ Verifies the validity of the attendance record compared to the others from the same employee.
            For the same employee we must have :
                * maximum 1 "open" attendance record (without check_out)
                * no overlapping time slices with previous employee records
        """
        for attendance in self:
            # we take the latest attendance before our check_in time and check it doesn't overlap with ours
            last_attendance_before_check_in = self.env['hr.attendance'].search([
                ('employee_id', '=', attendance.employee_id.id),
                ('check_in', '<=', attendance.check_in),
                ('id', '!=', attendance.id),
            ], order='check_in desc', limit=1)
            if last_attendance_before_check_in and last_attendance_before_check_in.check_out and last_attendance_before_check_in.check_out > attendance.check_in:
                raise exceptions.ValidationError(
                    _("Cannot create new attendance record for %(empl_name)s, the employee was already checked in on %(datetime)s") % {
                        'empl_name': attendance.employee_id.name,
                        'datetime': format_datetime(self.env, attendance.check_in, dt_format=False),
                    })


class ZkMachine(models.Model):
    _name = 'zk.machine'

    name = fields.Char(string='Machine IP', required=True)
    port_no = fields.Integer(string='No Port', required=True)
    address_id = fields.Many2one('res.partner', string='Adresse de travail')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.user.company_id.id)
    device_type = fields.Selection([
        ('entree', 'Entrée'),
        ('sortie', 'Sortie')
    ], string='Lieu')

    def device_connect(self, zk):
        try:
            conn = zk.connect()
            return conn
        except:
            return False

    def clear_attendance(self):
        for info in self:
            # print('self ---', self)
            try:
                machine_ip = info.name
                zk_port = info.port_no
                timeout = 30
                try:
                    zk = ZK(machine_ip, port=zk_port, timeout=timeout, password=0, force_udp=False, ommit_ping=False)
                except NameError:
                    raise UserError(_("Absence de librairie Veuillez l'installer avec 'pip3 install pyzk'."))
                conn = self.device_connect(zk)
                if conn:
                    conn.enable_device()
                    clear_data = zk.get_attendance()
                    if clear_data:

                        self._cr.execute("""delete from zk_machine_attendance""")
                        conn.disconnect()
                        raise UserError(_('Enregistrements de présence supprimés.'))
                    else:
                        raise UserError(
                            _("Impossible d'effacer le journal de présence. Êtes-vous sûr que le journal de présence n'est pas vide."))
                else:
                    raise UserError(
                        _('Impossible de se connecter au périphérique de présence. Veuillez utiliser le bouton Tester la connexion pour vérifier.'))
            except:
                raise ValidationError(
                    "Impossible d'effacer le journal de présence. Êtes-vous sûr que le dispositif de présence est connecté et que l'enregistrement n'est pas vide.")

    def getSizeUser(self, zk):
        """Checks a returned packet to see if it returned CMD_PREPARE_DATA,
        indicating that data packets are to be sent

        Returns the amount of bytes that are going to be sent"""
        command = unpack('HHHH', zk.data_recv[:8])[0]
        if command == CMD_PREPARE_DATA:
            size = unpack('I', zk.data_recv[8:12])[0]
            # print("size", size)ama
            return size
        else:
            return False

    def zkgetuser(self, zk):
        """Start a connection with the time clock"""
        try:
            users = zk.get_users()
            # print(users)
            return users
        except:
            return False

    @api.model
    def cron_download(self):
        machines = self.env['zk.machine'].search([])
        for machine in machines:
            machine.download_attendance()

    @api.model
    def auto_download_lack_attendance(self):
        print("auto_download_lack_attendance est exec", self)
        today = fields.Date.today()
        zk_machine_attendance = self.env['zk.machine.attendance'].search([
            ('punching_time', '>=', today),
            ('punching_time', '<=', today)
        ])
        nombre_jour = 0
        if not zk_machine_attendance:
            # raise ValidationError(f"Aucune présence trouvée du {self.date_from} au {self.date_to}")
            employees = self.env['hr.employee'].sudo().search([('device_id', '!=', False)])
            for nj in range(nombre_jour + 1):
                print("today", today, timedelta(days=0))
                date_actuelle = today + timedelta(days=nj)
                # print("Check in et check out",
                #       datetime.datetime(date_actuelle.year,date_actuelle.month,date_actuelle.day,0,0,0,0),
                #       datetime.datetime(date_actuelle.year,date_actuelle.month,date_actuelle.day,0,0,0,5))
                for employee in employees:
                    presence = self.env['hr.attendance'].sudo().create({
                        'employee_id': employee.id,
                        'check_in': datetime(date_actuelle.year, date_actuelle.month, date_actuelle.day, 0, 0,
                                                      0, 0),
                        'heur_planifie': employee.heur_arrive,
                        'heur_depart': employee.heur_depart,
                        'heure_sortie': 0.00,
                        'heure_entre': 0.00,
                        'tolerance': employee.tolerance,
                        'check_out': datetime(date_actuelle.year, date_actuelle.month, date_actuelle.day, 0, 0,
                                                       0, 5),
                        'visible': False,
                        'date_pointage': date_actuelle})
                    # print("Presence de no l'absent cree", presence)
            return
        # print("Zk_machine", zk_machine_attendance[0].check_in.date())

        # print(nombre_jour.days)
        for nj in range(nombre_jour + 1):
            # print(nj)
            date_actuelle = today + timedelta(days=nj)
            presences = self.env['hr.attendance'].sudo().search([
                ('date_pointage', '=', date_actuelle)
            ])
            # print("Date actuelle", date_actuelle)
            if not presences:
                zk = zk_machine_attendance.filtered(lambda s: s.punching_time.date() == date_actuelle)
                # print("Zk", zk)
                if zk:
                    employees = self.env['hr.employee'].sudo().search([('device_id', '!=', False)])
                    for employee in employees:
                        if zk_machine_attendance.filtered(lambda s: s.employee_id.id == employee.id):
                            zk_employee = zk.filtered(lambda s: s.employee_id.id == employee.id)
                            if zk_employee:
                                pointage_entrees = zk_employee.filtered(lambda s: s.punch_type == '0').mapped(
                                    'punching_time')
                                pointage_sorties = zk_employee.filtered(lambda s: s.punch_type == '1').mapped(
                                    'punching_time')
                                check_in = 0
                                check_out = 0
                                check_in_day = datetime(date_actuelle.year, date_actuelle.month,
                                                                 date_actuelle.day, 0, 0, 0, 0)
                                check_out_day = datetime(date_actuelle.year, date_actuelle.month,
                                                                  date_actuelle.day, 0, 0, 0, 5)
                                if pointage_entrees:
                                    # print("Les pointages entrees", pointage_entrees)
                                    check_in = min(pointage_entrees)
                                    # print("Checkin avant", pointage_entrees)
                                    check_in_hour = check_in.time().hour
                                    check_in_minute = check_in.time().minute
                                    # check_in = float(f"{check_in_hour}.{check_in_minute}")
                                    check_in = check_in_hour + check_in_minute / 60
                                    # print("Nouveau checkin", check_in)
                                    check_in_day = datetime(
                                        date_actuelle.year,
                                        date_actuelle.month,
                                        date_actuelle.day,
                                        hour=check_in_hour,
                                        minute=check_in_minute
                                    )
                                if pointage_sorties:
                                    # print("Pointage sortie")
                                    check_out = max(pointage_sorties)
                                    # check_out = check_out.time()
                                    check_out_hour = check_out.time().hour
                                    check_out_minute = check_out.time().minute
                                    check_out = check_out_hour + check_out_minute / 60
                                    check_out_day = datetime(
                                        date_actuelle.year,
                                        date_actuelle.month,
                                        date_actuelle.day,
                                        hour=check_out_hour,
                                        minute=check_out_minute
                                    )
                                # print("Check", check_in_day, check_out_day, employee.name)
                                # print("Check out", check_out_day)
                                # print("check_in apres", employee.name, check_in, check_out)
                                if check_in_day < check_out_day:
                                    # print("Check in check out de 1", check_in_day, check_out_day)
                                    presence = self.env['hr.attendance'].sudo().create({
                                        'employee_id': employee.id,
                                        'check_in': check_in_day,
                                        'check_out': check_out_day,
                                        'heur_planifie': employee.heur_arrive,
                                        'heur_depart': employee.heur_depart,
                                        'heure_entre': check_in,
                                        'heure_sortie': check_out,
                                        'tolerance': employee.tolerance,
                                        'visible': False,
                                        'is_check': True,
                                        'date_pointage': date_actuelle
                                    })
                                else:
                                    # print("Check in check out de 2222", check_in_day, check_out_day)
                                    presence = self.env['hr.attendance'].sudo().create({
                                        'employee_id': employee.id,
                                        'check_in': check_in_day,
                                        # 'check_out': check_out_day,
                                        'heur_planifie': employee.heur_arrive,
                                        'heur_depart': employee.heur_depart,
                                        'heure_entre': check_in,
                                        'heure_sortie': check_out,
                                        'tolerance': employee.tolerance,
                                        'visible': False,
                                        'is_check': True,
                                        'date_pointage': date_actuelle
                                    })
                                    # print("Check out ainsi", presence.check_out)
                                presence._compute_worked_hours()
                                # print("Presence cree", presence.employee_id.name, type(presence.heure_entre))
                        else:
                            # print("Employee qui n'a pas pointe", employee.name)
                            presence = self.env['hr.attendance'].sudo().create({
                                'employee_id': employee.id,
                                # 'check_in': date_actuelle,
                                'heur_planifie': employee.heur_arrive,
                                'heur_depart': employee.heur_depart,
                                'heure_sortie': 0.00,
                                'heure_entre': 0.00,
                                'tolerance': employee.tolerance,
                                # 'check_out': 0.0,
                                'visible': False,
                                'date_pointage': date_actuelle})
                            # print("Presence de l'absent cree", presence)
                    # date_pointage_zk = [z.date_pointage for z in zk]

    def download_attendance(self):
        _logger.info("++++++++++++Cron Executed++++++++++++++++++++++")
        zk_attendance = self.env['zk.machine.attendance']
        att_obj = self.env['hr.attendance']
        user_ids = []
        attendance = []
        all_employee_ids = []
        absence_aut_ids = []
        absence_ids = []
        employee_pointe_id = []
        conge_auto_ids = []
        print("zk_attendance", zk_attendance.search([]))
        today_time = datetime.today().strftime('%Y-%m-%d')
        today_heur = datetime.today().hour + datetime.today().minute / 60
        seq = self.env['sequence.log'].search([]).mapped('sequence_day')
        sequence = 1
        if seq:
            sequence = max(seq)

        for info in self:
            machine_ip = info.name
            zk_port = info.port_no
            timeout = 5  # modification 15 => 05

            try:
                zk = ZK(machine_ip, port=zk_port, timeout=timeout, password=0, force_udp=False, ommit_ping=False)
            except NameError:
                raise UserError(_("Module Pyzk introuvable. Veuillez l'installer avec 'pip3 install pyzk'."))
            conn = self.device_connect(zk)
            print("Avant conn", conn, machine_ip, zk_port)
            if conn:
                print("dans conn")
                # conn.disable_device() #Device Cannot be used during this time.
                try:
                    user = conn.get_users()
                except:
                    user = False
                # print('je passe n fois')
                # attendance = conn.get_attendance()
                try:
                    print("Debut du try")
                    attendance = conn.get_attendance()  # liste les présences
                    print("attendanceattendance", attendance)
                    for each in attendance:
                        pointage_time = each.timestamp.strftime('%Y-%m-%d')
                        if pointage_time == today_time:
                            user_ids.append(each.user_id)
                    today = datetime.today()
                    all_employee = self.env['hr.employee'].search([])
                    all_absence_aut = self.env['employee.absence'].search([])
                    all_absence = self.env['hr.absence'].search([])
                    conge_aut = self.env['hr.leave'].search([('state', '=', 'validate')])
                    print("Milieu du try")
                    for ep in all_employee:
                        all_employee_ids.append(ep.id)
                    for ab_aut in all_absence_aut:
                        absence_aut_ids.append(ab_aut.id)
                    for abs in all_absence:
                        absence_ids.append(abs.id)
                    for cg in conge_aut:
                        if cg.date_to.date() >= today.date() and cg.date_from.date() <= today.date():
                            conge_auto_ids.append(cg.employee_id.id)
                    print("FIn du try")
                except:
                    attendance = []
                print("Avant taille de attendance", attendance)
                if len(attendance) > 0:
                    for each in attendance:

                        atten_time = each.timestamp
                        atten_time = datetime.strptime(atten_time.strftime('%Y-%m-%d %H:%M:%S'), '%Y-%m-%d %H:%M:%S')
                        local_tz = pytz.timezone(
                            self.env.user.partner_id.tz or 'GMT')
                        local_dt = local_tz.localize(atten_time, is_dst=None)
                        utc_dt = local_dt.astimezone(pytz.utc)
                        utc_dt = utc_dt.strftime("%Y-%m-%d %H:%M:%S")
                        pointage_date = each.timestamp.strftime('%Y-%m-%d')
                        pointage_heur = each.timestamp.hour + each.timestamp.minute / 60
                        get_user_id = self.env['hr.employee'].search(
                            [('device_id', '=', each.user_id)])
                        duplicate_atten_ids = zk_attendance.search(
                            [('device_id', '=', each.user_id), ('punching_time', '=', atten_time)])
                        now = datetime.now()
                        start_time = now.replace(hour=18, minute=50, second=0, microsecond=0)
                        end_time = now.replace(hour=23, minute=59, second=0, microsecond=0)
                        print("avance device_type", duplicate_atten_ids)
                        if info.device_type == "entree":
                            """
                                =============================== La borne d'entrée ===========================
                            """
                            print("Borne d'entree")
                            if user:
                                # print("if de user", user)
                                for uid in user:

                                    if uid.user_id == each.user_id and pointage_date == today_time:

                                        # recuperation de des employés dont l'id dans la conf = à ceux de la machine
                                        if get_user_id:

                                            if get_user_id.id not in employee_pointe_id:
                                                employee_pointe_id.append(get_user_id.id)

                                            if not duplicate_atten_ids:
                                                zk_attendance.create({'employee_id': get_user_id.id,
                                                                      'device_id': each.user_id,
                                                                      'punch_type': '0',
                                                                      'punching_time': atten_time,
                                                                      'address_id': info.address_id.id,
                                                                      'compare_date': pointage_date,
                                                                      'compare': str(pointage_date)})
                                            print("VErif heure", start_time)
                                            if start_time < now <= end_time:
                                                if str(pointage_date) == str(today_time):
                                                    att_var = att_obj.search([('employee_id', '=', get_user_id.id),
                                                                              ('is_check', '=', True),
                                                                              ('date_pointage', '=', today_time)])
                                                    if not att_var:
                                                        print("Creation new", get_user_id.name)
                                                        att_obj.create({'employee_id': get_user_id.id,
                                                                        'check_in': atten_time,
                                                                        'check_out': atten_time,
                                                                        'heur_planifie': get_user_id.heur_arrive,
                                                                        'heur_depart': get_user_id.heur_depart,
                                                                        'heure_entre': pointage_heur,
                                                                        'tolerance': get_user_id.tolerance,
                                                                        'visible': False,
                                                                        'sequence': sequence,
                                                                        'is_check': True,
                                                                        'date_pointage': pointage_date})
                                                        print("Okay", att_obj)

                                                    else:
                                                        att_var[-1].write(
                                                            {
                                                                'check_out': atten_time,
                                                                'heur_planifie': get_user_id.heur_arrive,
                                                                'heur_depart': get_user_id.heur_depart,
                                                                'tolerance': get_user_id.tolerance,
                                                            })


                        elif info.device_type == 'sortie':
                            """
                               =========================== La borne de sortie =========================
                            """
                            print("Borne sortie")
                            if user:
                                # print("User obtenu", user)
                                for uid in user:

                                    if uid.user_id == each.user_id and pointage_date == today_time:
                                        # recuperation de des employés dont l'id dans la conf = à ceux de la machine
                                        if get_user_id:
                                            print("Getuserid")
                                            if duplicate_atten_ids:
                                                pass
                                            else:
                                                zk_attendance.create({'employee_id': get_user_id.id,
                                                                      'device_id': each.user_id,
                                                                      'punch_type': '1',
                                                                      'punching_time': atten_time,
                                                                      'address_id': info.address_id.id,
                                                                      'compare_date': pointage_date,
                                                                      'compare': str(pointage_date)})

                                            if start_time < now <= end_time:
                                                if str(pointage_date) == str(today_time):
                                                    print("Creation")
                                                    att_var = att_obj.search([('employee_id', '=', get_user_id.id),
                                                                              ('is_check', '=', True),
                                                                              ('date_pointage', '=', today_time)])

                                                    if att_var:
                                                        print("Modification")
                                                        att_var[-1].write(
                                                            {'check_out': atten_time, 'heure_sortie': pointage_heur})

                    get_employer = self.env['hr.employee'].search(
                        [('device_id', '!=', False), ('device_id', 'not in', user_ids)])
                    for val in get_employer:

                        # si l'id n'est pas dans la liste des absences autorisées
                        if val.id not in conge_auto_ids:
                            absence = self.env['hr.absence']
                            duplicate_absence = absence.search(
                                [('employee_id', '=', val.id), ('date_absence', '=', today_time)])
                            today = datetime.today()
                            now = datetime.now()
                            att_time_in = now.replace(hour=00, minute=00, second=0, microsecond=0)
                            att_time_out = now.replace(hour=00, minute=00, second=0, microsecond=5)
                            att_in = att_time_in.strftime("%Y-%m-%d %H:%M:%S")
                            att_out = att_time_out.strftime("%Y-%m-%d %H:%M:%S")
                            start_time = now.replace(hour=18, minute=50, second=0, microsecond=0)
                            end_time = now.replace(hour=23, minute=59, second=0, microsecond=0)

                            if start_time < now <= end_time:
                                if not duplicate_absence:
                                    att_var0 = att_obj.search([('employee_id', '=', val.id),
                                                               ('is_check', '=', True),
                                                               ('date_pointage', '=', today_time)])
                                    if not att_var0:
                                        absence.create({
                                            'employee_id': val.id,
                                            'date_absence': today_time,
                                            'heur_perdu': -8
                                        })

                                        att_var0.create({'employee_id': val.id,
                                                         'check_in': att_in,
                                                         'heur_planifie': val.heur_arrive,
                                                         'heur_depart': val.heur_depart,
                                                         'heure_sortie': 0.00,
                                                         'heure_entre': 0.00,
                                                         'tolerance': val.tolerance,
                                                         'check_out': att_out,
                                                         'visible': False,
                                                         'date_pointage': today})

                    for i in employee_pointe_id:

                        nbre_ocurence = employee_pointe_id.count(i)
                        if nbre_ocurence == 1:
                            user_ocu = self.env['hr.attendance'].search([('employee_id', '=', i)])
                            if user_ocu:
                                if user_ocu[-1].heur_depart + 0.5 < today_heur and user_ocu[-1].visible == False:
                                    user_ocu[-1].write({'visible': True,
                                                        'heure_sortie': user_ocu[-1].heur_depart})
                # zk.enableDevice()
                conn.disconnect
                return True
            else:
                raise UserError(_("Impossible d'obtenir le journal des présences, veuillez réessayer plus tard."))
        else:
            raise UserError(_('Connexion impossible, veuillez vérifier les paramètres et les connexions réseau.'))
