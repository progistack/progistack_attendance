from odoo import api, models, fields
import datetime
from calendar import monthrange


class ReportPresence(models.TransientModel):
    _name = "report.presence"

    def _get_default_start_date(self):
        today = datetime.date.today()
        weekday = today.weekday()
        if today.day > datetime.timedelta(weekday).days + 7:
            return datetime.date(
                today.year,
                today.month,
                today.day - datetime.timedelta(weekday).days - 7
            )
        else:
            if today.month - 1 >= 1:
                return datetime.date(
                    today.year,
                    today.month - 1,
                    today.day + monthrange(today.year, today.month - 1)[1] - datetime.timedelta(weekday).days - 7
                )
            else:
                return datetime.date(
                    today.year - 1,
                    12,
                    today.day + monthrange(today.year, 12)[1] - datetime.timedelta(weekday).days - 7
                )

    def _get_default_end_date(self):
        today = datetime.date.today()
        weekday = today.weekday()

        if today.day > datetime.timedelta(weekday).days + 3:
            return datetime.date(
                today.year,
                today.month,
                today.day - datetime.timedelta(weekday).days - 3
            )
        else:
            if today.month - 1 >= 1:
                return datetime.date(
                    today.year,
                    today.month - 1,
                    today.day + monthrange(today.year, today.month - 1)[1] - datetime.timedelta(weekday).days - 3
                )
            else:
                return datetime.date(
                    today.year - 1,
                    12,
                    today.day + monthrange(today.year, 12)[1] - datetime.timedelta(weekday).days - 3
                )

    start_date = fields.Date(string="Date de début", default=_get_default_start_date)
    end_date = fields.Date(string="Date de fin", default=_get_default_end_date)
    employee = fields.Many2one('hr.employee', string="Employee")
    with_present = fields.Boolean(string='Exporter avec les présents')

    def confirmer(self):

        #
        # print("presence", all_presences)
        # tbl = {}
        # for presence in all_presences:
        #     pointage = presence.date_pointage
        #     arrivee = presence.heur_planifie
        #     entre = presence.heure_entre
        #     depart = presence.heur_depart
        #     sortie = presence.heure_sortie
        #     work = presence.worked_hour
        #     status = presence.statut
        #     tbl.update({
        #         'pointage':pointage,
        #         'arrivee': arrivee,
        #         'entre': entre,
        #         'depart': depart,
        #         'sortie': sortie,
        #         'work': work,
        #         'status': status,
        #     })
        # print(tbl)
        start_date = self.start_date
        end_date = self.end_date
        employee = self.env['hr.employee'].search([])
        data = {'start_date': start_date, 'end_date': end_date, 'employee': employee, 'with_present': self.with_present}
        return self.env.ref('progistack_attendance.report_secii_synthese_partner').with_context(
            employee_id=self.employee.id).report_action(self, data=data)

    def cancel(self):
        print('cancel')
